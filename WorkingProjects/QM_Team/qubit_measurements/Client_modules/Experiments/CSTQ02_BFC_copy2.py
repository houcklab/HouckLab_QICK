# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

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


# from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
# from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift
# from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF import SingleShotProgramFF
# from q4diamond.Client_modules.Experiment_Scripts.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF

soc, soccfg = makeProxy()

def ramp_to(yoko, target, step=0.001, delay=0.01):
    if target > 10:
        raise ValueError("Voltage too high")
    current = float(yoko.query(":SOUR:LEV?"))
    values = np.arange(current, target, step if target > current else -step)
    for v in values:
        yoko.write(f":SOUR:LEV {v}")
        time.sleep(delay)
    yoko.write(f":SOUR:LEV {target}")  # land exactly on target

# -------------------- local fit helpers --------------------
def lorentzian_dip(f, y0, A, f0, gamma):
    # dip: baseline - lorentzian
    return y0 - A / (1.0 + ((f - f0) / gamma) ** 2)

def lorentzian_peak(f, y0, A, f0, gamma):
    # peak: baseline + lorentzian
    return y0 + A / (1.0 + ((f - f0) / gamma) ** 2)

def fit_lorentzian_feature(x, y, fit_dip=True):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    # initial guesses
    y_max = np.max(y)
    y_min = np.min(y)
    x_span = np.max(x) - np.min(x)

    if fit_dip:
        idx0 = np.argmin(y)
        y0_guess = np.median(y)
        A_guess = max(y0_guess - y_min, 1e-12)
    else:
        idx0 = np.argmax(y)
        y0_guess = np.median(y)
        A_guess = max(y_max - y0_guess, 1e-12)

    f0_guess = x[idx0]
    gamma_guess = max(x_span / 20.0, 1e-6)

    model = lorentzian_dip if fit_dip else lorentzian_peak
    p0 = [y0_guess, A_guess, f0_guess, gamma_guess]

    bounds = (
        [-np.inf, 0.0, np.min(x), 1e-12],
        [ np.inf, np.inf, np.max(x), x_span]
    )

    popt, pcov = curve_fit(model, x, y, p0=p0, bounds=bounds, maxfev=50000)
    perr = np.sqrt(np.diag(pcov))
    yfit = model(x, *popt)

    # goodness-of-fit / uncertainty propagation
    residuals = y - yfit
    rss = np.sum(residuals**2)

    return {
        "popt": popt,
        "pcov": pcov,
        "perr": perr,
        "yfit": yfit,
        "rss": rss,
        "model": model,
    }

def find_two_tone_peaks(x_pts, avgamp0, min_sep_mhz=0.1,
                        prominence_fraction=0.25, smooth_window=5):
    """
    Locate up to two prominent peaks in a two-tone spectrum.

    The algorithm:
      1. Savitzky-Golay smooth to suppress single-sample noise spikes.
      2. Find peaks whose *prominence* exceeds prominence_fraction * (max-min).
         Prominence measures how much a peak rises above its surrounding
         landscape, so noise bumps riding on top of a single broad peak are
         rejected while genuine second resonances (which rise from the baseline)
         are kept.
      3. Keep the two tallest qualifying peaks, sorted by frequency.
      4. Fall back to the global maximum if no peak clears the prominence bar.

    Parameters
    ----------
    min_sep_mhz : float
        Minimum allowed separation between two returned peaks [MHz].
    prominence_fraction : float
        Prominence threshold as a fraction of the spectrum's dynamic range.
        0.25 works well for typical two-tone SNR.
    smooth_window : int
        Savitzky-Golay window length in samples (must be odd; set to 1 to skip).
    """
    x_pts   = np.asarray(x_pts,   dtype=float)
    avgamp0 = np.asarray(avgamp0, dtype=float)
    n = len(avgamp0)

    # --- trivial case -------------------------------------------------------
    if n <= 2:
        best = int(np.argmax(avgamp0))
        return {"peak_inds": [best], "peak_freqs": x_pts[[best]],
                "peak_vals": avgamp0[[best]], "peak_sep": None}

    # --- 1. Smooth ----------------------------------------------------------
    sw = max(3, int(smooth_window) | 1)          # must be odd, at least 3
    sw = min(sw, n if n % 2 == 1 else n - 1)     # cannot exceed array length
    sig = savgol_filter(avgamp0, window_length=sw, polyorder=2) if sw >= 3 else avgamp0.copy()

    # --- 2. Prominence threshold --------------------------------------------
    amp_range = sig.max() - sig.min()
    if amp_range < 1e-12:
        best = int(np.argmax(sig))
        return {"peak_inds": [best], "peak_freqs": x_pts[[best]],
                "peak_vals": avgamp0[[best]], "peak_sep": None}
    prom_thresh = prominence_fraction * amp_range

    # --- 3. Minimum distance in samples -------------------------------------
    dx = abs(float(x_pts[1] - x_pts[0])) if n > 1 else 1.0
    min_dist = max(1, int(round(min_sep_mhz / dx)))

    # --- 4. Find prominent peaks --------------------------------------------
    peak_inds, _ = find_peaks(sig, prominence=prom_thresh, distance=min_dist)

    if len(peak_inds) == 0:
        # Nothing cleared the prominence bar — return the global maximum only
        best = int(np.argmax(sig))
        return {"peak_inds": [best], "peak_freqs": x_pts[[best]],
                "peak_vals": avgamp0[[best]], "peak_sep": None}

    # --- 5. Keep the two tallest, sorted by frequency -----------------------
    if len(peak_inds) > 2:
        order = np.argsort(sig[peak_inds])[::-1]
        peak_inds = np.sort(peak_inds[order[:2]])

    if len(peak_inds) == 2:
        i0, i1 = int(peak_inds[0]), int(peak_inds[1])
        return {
            "peak_inds": [i0, i1],
            "peak_freqs": np.array([x_pts[i0], x_pts[i1]]),
            "peak_vals":  np.array([avgamp0[i0], avgamp0[i1]]),
            "peak_sep":   abs(float(x_pts[i1]) - float(x_pts[i0])),
        }
    else:
        i0 = int(peak_inds[0])
        return {
            "peak_inds": [i0],
            "peak_freqs": np.array([x_pts[i0]]),
            "peak_vals":  np.array([avgamp0[i0]]),
            "peak_sep":   None,
        }


def save_two_tone_plot(x_pts, avgi, avgq, avgamp0, peak_info, current_voltage, attempt_idx, save_dir):
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    base = os.path.join(save_dir, f"TwoTone_{attempt_idx:03d}_{timestamp}")

    plt.figure(figsize=(8, 5))
    plt.plot(x_pts, avgi, '.-', label="I")
    plt.plot(x_pts, avgq, '.-', label="Q")
    for k, idx in enumerate(peak_info["peak_inds"]):
        plt.axvline(x_pts[idx], linestyle='--', label=f"Peak {k+1}: {x_pts[idx]:.6f} MHz")
    plt.xlabel("Qubit Frequency (MHz)")
    plt.ylabel("a.u.")
    plt.title(f"Two-tone IQ, V={current_voltage:.6f} V")
    plt.legend()
    plt.tight_layout()
    plt.savefig(base + "_IQ.png", dpi=300, bbox_inches="tight")
    plt.close()

    plt.figure(figsize=(8, 5))
    plt.plot(x_pts, avgamp0, '.-', label="|I+iQ|^2")
    for k, idx in enumerate(peak_info["peak_inds"]):
        plt.axvline(x_pts[idx], linestyle='--', label=f"Peak {k+1}: {x_pts[idx]:.6f} MHz")
        plt.plot(x_pts[idx], avgamp0[idx], 'o')
    plt.xlabel("Qubit Frequency (MHz)")
    plt.ylabel("a.u.")
    sep_txt = "None" if peak_info["peak_sep"] is None else f"{peak_info['peak_sep']:.6f} MHz"
    plt.title(f"Two-tone amplitude, V={current_voltage:.6f} V, sep={sep_txt}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(base + "_amp.png", dpi=300, bbox_inches="tight")
    plt.close()

    return base


def choose_next_voltage(current_v, dv, vmin, vmax, direction):
    proposed = current_v + direction * dv

    if proposed > vmax:
        direction = -1
        proposed = current_v + direction * dv

    if proposed < vmin:
        direction = +1
        proposed = current_v + direction * dv

    proposed = min(max(proposed, vmin), vmax)
    return proposed, direction


"""
'4': {'Readout': {'Frequency': 7288.505, 'Gain': 1400}, # 1500 is too high # 1250
          'Qubit': {'Frequency': 2306.3, 'Gain': 26060,  "pi2_Gain": 26060 // 2,"sigma": 0.06, "flattop_length": None}, 
          'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/CSTQ02/RFSOC/Q4//"},
^ with Q4 charge line 
"""

temp_dir_Q4 = "C:/Users/ece-houck-j409/Documents/Data/2026-3-9_BC_Cooldown/CSTQ02/RFSOC/Q4//"
############## New TATQ03 (No Charge Lines) ############################
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6757.958, 'Gain': 4500},
          'Qubit': {'Frequency': 1400, 'Gain': 5000,  "pi2_Gain": 3975 // 2,"sigma": 1, "flattop_length": 0.5},
          'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/CSTQ02/RFSOC/Q1//"},
    '2': {'Readout': {'Frequency': 7191.979, 'Gain': 4000}, # coarsely tuned to 4000, seeing behavior at 4500
          'Qubit': {'Frequency': 3052.418, 'Gain': 3975, "pi2_Gain": 3975 // 2, "sigma": 0.2 , "flattop_length": None}, # qubit, T1 found
          'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/CSTQ02/RFSOC/Q2//"},
    '3': {'Readout': {'Frequency': 6879.336, 'Gain': 3500},
          'Qubit': {'Frequency': 1719.8273, 'Gain': 5000,  "pi2_Gain": 3975 // 2,"sigma": 1 , "flattop_length": 1}, # qubit found 1719.8273
          'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/CSTQ02/RFSOC/Q3//"},
    '4': {'Readout': {'Frequency': 7288.409333, 'Gain': 4825}, # 2800 pretty good, 3000 maybe too high (.433 is very close and shouldnt move by too much)
          'Qubit': {'Frequency':    2306.3, 'Gain': 5506,  "pi2_Gain": 5506 // 2,"sigma": 0.22, "flattop_length": None}, # qubit, 7468 was the previous pi pulse with sigma = 0.15, 5396 0.225 6435 2603.33 used for ramsey
          'outerfoldername': "V:/t1Team/Data/2026-3-9_BFC_Cooldown/CSTQ02/RFSOC/Q4//"},
    '5': {'Readout': {'Frequency': 6970.6, 'Gain': 5500}, # 3500 is okay, 5000 is maybe okay, 7000 is too much, 6500 is maybe too much
          'Qubit': {'Frequency':  2758.442425742575, 'Gain': 3210, "pi2_Gain": 3500 // 2, "sigma": 0.1, "flattop_length": None}, #2756.685
          'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/CSTQ02/RFSOC/Q5//"}, # qubit, T1 found
    '6': {'Readout': {'Frequency': 7070.719, 'Gain': 4000},
          'Qubit': {'Frequency': 2000, 'Gain': 5000,  "pi2_Gain": 3975 // 2, "sigma": 1 , "flattop_length": 1}, # cant find
          'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/CSTQ02/RFSOC/Q6//"},
    }
############## End Can D ############################
# yoko
start_voltage = 0.007 # sets voltage for the entire experiment #0.0059 working for good T2Rs

rm = pyvisa.ResourceManager()
yoko = rm.open_resource('GPIB1::9::INSTR')
# yoko.write("*RST")
yoko.write(":SOUR:FUNC VOLT")
yoko.write(":OUTP ON")
ramp_to(yoko, start_voltage)

yoko_fixed = False

# Readout

Qubit_Readout = 4
Qubit_Pulse = 4
outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

Constant2Tone = False
tl = {"tone_length": 151}
ConstantTone = False  # determine cavity frequency

RunTransmissionSweep = False # determine cavity frequency
RunTransmissionSweeps = False
ts = {"start_ts_gain": 500, "end_ts_gain": 8000, "ts_step" : 500}

Run2ToneSpec =  False
RunTrans_QubitSpec = False
RunChargeSweep = False
charge_params = {"voltage_start" : 0.0, "voltage_end" : 10, "voltage_step": 0.001, } # 0.0001 has two periods in it
Spec_relevant_params = {"qubit_gain": 7468, "SpecSpan": 1, "SpecNumPoints": 101, # 750 works Q5
                        "qubit_length" : 2, # length of flattop pulse when gauss = False # 9.5 worked
                        "reps": 10, 'rounds': 10,
                        'Gauss': True, "sigma": 2, "gain": 700,
                        'relax_delay' : 1500} # 700 used for charge sweeps

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

    # two-tone spec settings used during the search
    "SpecSpan": 1.0,
    "SpecNumPoints": 101,
    "reps": 10,
    "rounds": 10,
    "relax_delay": 1500,
    "Gauss": True,
    "sigma": 2,
    "gain": 700,
    "qubit_length": 2,

    # quasi-CW settings once the peaks are separated enough
    "qcw_repetitions": 100,
    "qcw_relax_delay": 1500,
}

ModifiedRamsey_params = {
    # --- two-tone search settings (same role as TwoToneChargeDispersion_params) ---
    "df": 0.5,                  # required peak separation in MHz before running Ramsey
    "dV": 0.0005,               # voltage step size [V]
    "voltage_min": 0.000,       # absolute lower voltage bound [V]
    "voltage_max": 0.010,       # absolute upper voltage bound [V]
    "max_voltage_tries": 1000,  # max search steps per cycle
    "num_cycles": 1000,         # how many search -> Ramsey cycles to run

    # two-tone spec settings used during the voltage search
    "SpecSpan": 1.0,
    "SpecNumPoints": 101,
    "reps": 10,
    "rounds": 10,
    "relax_delay": 1500,
    "Gauss": True,
    "sigma": 2,
    "gain": 700,
    "qubit_length": 2,

    # --- Modified Ramsey settings ---
    # tau is computed automatically as 1 / (2 * peak_sep_MHz)
    # f_ge is set automatically to the higher-frequency peak
    # No relax delay: the measurement collapses the qubit and acts as reset.
    "mr_reps": 500,             # number of single-shot Ramsey measurements per cycle
    # "mr_reps": 10000,             # number of single-shot Ramsey measurements per cycle
}

RunModifiedRamsey_Control = True  # two-tone search -> half-period step -> sweet-spot interpolation -> Ramsey

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
                         "max_gain": 8000, 'number_of_steps': 501,
                         "reps": 10, 'rounds': 10,
                         'relax_delay': 3500}  #Always change the max gain if you don't see it, also compare what you get with Transmission data

RunT1 = False
RunT2 = False
T1T2_params = {"T1_step": 40, "T1_expts": 60, "T1_reps": 20, "T1_rounds": 20, # 80 100 30 30
               "T2_step": 0.1, "T2_expts": 201, "T2_reps": 20, "T2_rounds": 20, "freq_shift": 0.0,
               "relax_delay": 3500, # 5000
               'repetitions': 1000}

RunT1T2E = False

RunT1T2RT2E = False

RunT2E = False
T2E_params = {"T2_max_us": 200, "T2_expts": 201, "T2_reps": 25, "T2_rounds": 25, "freq_shift": 0.0,
               "relax_delay": 3500, 'num_pi_pulses': 1, #need odd number of pulses
              "rotation_angle": None,
              "min_max": None,
              'repetitions': 3000}

SingleShot = False
SS_params = {"Shots": 100, "Readout_Time": 15, "ADC_Offset": 1, "Qubit_Pulse": [Qubit_Pulse],
             'number_of_pulses': 1, 'relax_delay': 3500, "pi2_SS": False} # keep at 15

RunT1SS = False
T1SS_params = {"T1_step": 80, "T1_expts": 100,
               "reps": 2000,
               'angle': 0, 'threshold': 0,
               "relax_delay": 8000,
               'calibrate_SS': True,
               'repetitions': 3000}

SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 4000, "gain_stop": 7000, "gain_pts": 30, "span": 0.00000001, "trans_pts": 2}

SingleShot_QubitOptimize = False
SS_Q_params = {"q_gain_span": 250, "q_gain_pts" : 500, "q_freq_span": 0.000001, "q_freq_pts": 2,
               'number_of_pulses': 11} # for optimizing pi/2 pulse, set the gain to the half of its value and optimize for n=2


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
    "TransSpan": 0.75,  ### 0.75 MHz, span will be center+/- this parameter
    "TransNumPoints": 301,  ### number of points in the transmission frequecny
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
    config["reps"] = 20   # fast axis number of points
    config["rounds"] = 20 # slow axis number of points

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

    sig = data_trans['data']['results'][0][0][0] + 1j * data_trans['data']['results'][0][0][1]
    y_pts = np.abs(sig)
    x_pts = np.asarray(data_trans['data']['fpts'])

    # -------------------- fit dip or peak --------------------
    # cavity_min=True means use the dip; otherwise fit the peak
    fit_is_dip = bool(cavity_min)
    fit_result = fit_lorentzian_feature(x_pts, y_pts, fit_dip=fit_is_dip)

    popt = fit_result["popt"]
    perr = fit_result["perr"]

    y0_fit, A_fit, f0_fit, gamma_fit = popt
    dy0_fit, dA_fit, df0_fit, dgamma_fit = perr

    # update config with fitted center frequency
    config["pulse_freq"] = f0_fit

    # compare to requested/input center
    freq_deviation = f0_fit - resonator_frequency_center

    feature_name = "dip" if fit_is_dip else "peak"
    print(f"Lorentzian {feature_name} fit:")
    print(f"  f0       = {f0_fit:.6f} ± {df0_fit:.6f}")
    print(f"  gamma    = {gamma_fit:.6f} ± {dgamma_fit:.6f}")
    print(f"  baseline = {y0_fit:.6f} ± {dy0_fit:.6f}")
    print(f"  depth    = {A_fit:.6f} ± {dA_fit:.6f}")
    print(f"  deviation from resonator_frequency_center ({resonator_frequency_center:.6f}) = {freq_deviation:+.6f}")
    print(f"Cavity frequency found at: {config['pulse_freq']:.6f}")

    # -------------------- plot fit over signal --------------------
    x_fit = np.linspace(np.min(x_pts), np.max(x_pts), 1000)
    y_fit = fit_result["model"](x_fit, *popt)

    fig_num_fit = 100
    while plt.fignum_exists(fig_num_fit):
        fig_num_fit += 1

    min_freq = Instance_trans.peakFreq_min

    plt.figure(fig_num_fit)
    plt.plot(x_pts, y_pts, 'o', label='|sig| data')
    plt.plot(x_fit, y_fit, '-', linewidth=2,
             label=f'Lorentzian {feature_name} fit\nf0={f0_fit:.6f} ± {df0_fit:.6f}')
    plt.axvline(resonator_frequency_center, linestyle='--', color='gray',
                label=f'input center = {resonator_frequency_center:.6f}')
    plt.axvline(f0_fit, linestyle=':', color='red',
                label=f'fit center = {f0_fit:.6f}')
    plt.axvline(min_freq, linestyle=':', color='blue',
                label=f'min freq = {min_freq:.6f}')
    plt.xlabel("Frequency")
    plt.ylabel("Amplitude (a.u.)")
    plt.title("Transmission sweep with Lorentzian fit")
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

    config["qubit_length"] = Spec_relevant_params["qubit_length"]
    config["SpecSpan"] = Spec_relevant_params["SpecSpan"]
    config["SpecNumPoints"] = Spec_relevant_params["SpecNumPoints"]
    config["step"] = 2 * config["SpecSpan"] / config["SpecNumPoints"]
    config["start"] = qubit_frequency_center - config["SpecSpan"]
    config["expts"] = config["SpecNumPoints"]
    config['relax_delay'] = Spec_relevant_params['relax_delay']

    Instance_specSlice = QubitSpecSliceFF(
        path="QubitSpecFF",
        cfg=config,
        soc=soc,
        soccfg=soccfg,
        outerFolder=outerFolder
    )
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=False, figNum=2) # can change to True
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
    QubitSpecSliceFF.save_config(Instance_specSlice)

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
            QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
            QubitSpecSliceFF.save_config(Instance_specSlice)

            x_pts = np.array(data_specSlice["data"]["x_pts"])
            avgi = np.array(data_specSlice["data"]["avgi"][0][0])
            avgq = np.array(data_specSlice["data"]["avgq"][0][0])
            sig = avgi + 1j * avgq
            avgamp0 = np.abs(sig) ** 2

            peak_info = find_two_tone_peaks(x_pts, avgamp0, min_sep_mhz=0.1)

            save_base = save_two_tone_plot(
                x_pts=x_pts,
                avgi=avgi,
                avgq=avgq,
                avgamp0=avgamp0,
                peak_info=peak_info,
                current_voltage=current_voltage,
                attempt_idx=attempt_idx + cycle_idx * max_tries,
                save_dir=save_dir
            )

            with open(save_base + "_summary.txt", "w") as f:
                f.write(f"cycle_idx: {cycle_idx}\n")
                f.write(f"attempt_idx: {attempt_idx}\n")
                f.write(f"current_voltage: {current_voltage:.9f}\n")
                f.write(f"peak_freqs: {peak_info['peak_freqs']}\n")
                f.write(f"peak_vals: {peak_info['peak_vals']}\n")
                f.write(f"peak_sep: {peak_info['peak_sep']}\n")
                f.write(f"df_required: {df_required}\n")

            if peak_info["peak_sep"] is not None and peak_info["peak_sep"] >= df_required:
                if TwoToneChargeDispersion_params["use_upper_peak"]:
                    chosen_probe_freq = float(np.max(peak_info["peak_freqs"]))
                else:
                    chosen_probe_freq = float(np.min(peak_info["peak_freqs"]))

                chosen_peak_sep = float(peak_info["peak_sep"])
                print(
                    f"[TwoToneChargeDispersion] Cycle {cycle_idx + 1}: success, "
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
    save_dir_mr = os.path.join(outerFolder, "ModifiedRamsey")
    os.makedirs(save_dir_mr, exist_ok=True)

    df_required_mr = ModifiedRamsey_params["df"]
    dV_mr = ModifiedRamsey_params["dV"]
    voltage_min_mr = max(0.0, ModifiedRamsey_params["voltage_min"])
    voltage_max_mr = ModifiedRamsey_params["voltage_max"]
    max_tries_mr = ModifiedRamsey_params["max_voltage_tries"]
    num_cycles_mr = ModifiedRamsey_params["num_cycles"]

    ModifiedRamsey_params.setdefault("hysteresis_low", 0.4)
    ModifiedRamsey_params.setdefault("hysteresis_high", 0.6)
    ModifiedRamsey_params.setdefault("window_ms", 0.1)

    current_voltage_mr = float(yoko.query(":SOUR:LEV?"))
    direction_mr = +1

    cycle_summary_mr = []

    for cycle_idx_mr in range(num_cycles_mr):
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
            QubitSpecSliceFF.save_data(Instance_specSlice_mr, data_specSlice_mr)
            QubitSpecSliceFF.save_config(Instance_specSlice_mr)

            x_pts_mr = np.array(data_specSlice_mr["data"]["x_pts"])
            avgi_mr = np.array(data_specSlice_mr["data"]["avgi"][0][0])
            avgq_mr = np.array(data_specSlice_mr["data"]["avgq"][0][0])
            sig_mr = avgi_mr + 1j * avgq_mr
            avgamp0_mr = np.abs(sig_mr) ** 2

            peak_info_mr = find_two_tone_peaks(x_pts_mr, avgamp0_mr, min_sep_mhz=0.1)

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

            if (peak_info_mr["peak_sep"] is not None
                    and peak_info_mr["peak_sep"] >= df_required_mr):
                # always use the higher-frequency peak as f_ge
                chosen_probe_freq_mr = float(np.max(peak_info_mr["peak_freqs"]))
                chosen_peak_sep_mr = float(peak_info_mr["peak_sep"])
                print(
                    f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}: peaks found, "
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

        # ---------- classify shots and build parity trace ----------
        raw_i_mr = np.ravel(np.array(data_mr["data"]["shots_i"]))
        raw_q_mr = np.ravel(np.array(data_mr["data"]["shots_q"]))
        iq_mr = np.column_stack([raw_i_mr, raw_q_mr])

        kmeans_mr = KMeans(n_clusters=2, random_state=0, n_init=20)
        kmeans_mr.fit_predict(iq_mr)
        centers_mr = kmeans_mr.cluster_centers_

        c0_mr = centers_mr[0]
        c1_mr = centers_mr[1]
        normal_mr = c1_mr - c0_mr
        midpoint_mr = 0.5 * (c0_mr + c1_mr)
        scores_mr = (iq_mr - midpoint_mr) @ normal_mr
        binary_states_mr = (scores_mr > 0).astype(int)

        # relabel so state 0 is the more-populated blob
        n0_mr = np.sum(binary_states_mr == 0)
        n1_mr = np.sum(binary_states_mr == 1)
        if n1_mr > n0_mr:
            binary_states_mr = 1 - binary_states_mr
            c0_mr, c1_mr = c1_mr, c0_mr
            normal_mr = c1_mr - c0_mr
            midpoint_mr = 0.5 * (c0_mr + c1_mr)
            scores_mr = (iq_mr - midpoint_mr) @ normal_mr

        # approximate time axis: pi/2 + tau + pi/2 + 0.05 sync + readout (no relax)
        pulse_length_us = qubit_sigma * 4
        rep_period_us = 2 * pulse_length_us + tau_us_mr + 0.05 + config_mr["readout_length"]
        elapsed_ms_mr = np.arange(len(raw_i_mr)) * rep_period_us * 1e-3

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

        # IQ scatter with separator
        plt.figure(figsize=(6, 6))
        plt.plot(raw_i_mr[binary_states_mr == 0], raw_q_mr[binary_states_mr == 0],
                 ".", alpha=0.5, label="State 0 (upper parity)")
        plt.plot(raw_i_mr[binary_states_mr == 1], raw_q_mr[binary_states_mr == 1],
                 ".", alpha=0.5, label="State 1 (lower parity)")
        plt.plot(c0_mr[0], c0_mr[1], "o", markersize=10)
        plt.plot(c1_mr[0], c1_mr[1], "o", markersize=10)
        if vertical_line_mr:
            plt.axvline(midpoint_mr[0], linestyle="--", linewidth=2, label="Separator")
        else:
            plt.plot(I_line_mr, Q_line_mr, "--", linewidth=2, label="Separator")
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
        plt.savefig(base_mr + "_iq_labeled.png", dpi=300, bbox_inches="tight")
        plt.close()

        # raw parity binary trace
        plt.figure(figsize=(10, 4))
        plt.step(elapsed_ms_mr, binary_states_mr, where="post", linewidth=1.5)
        plt.plot(elapsed_ms_mr, binary_states_mr, "o", markersize=2)
        plt.xlabel("Time since start (ms)")
        plt.ylabel("Parity state (0=upper, 1=lower)")
        plt.yticks([0, 1])
        plt.ylim(-0.1, 1.1)
        plt.title(
            f"Cycle {cycle_idx_mr + 1}: Modified Ramsey parity trace\n"
            f"tau={tau_us_mr:.4f} us, df={chosen_peak_sep_mr:.4f} MHz"
        )
        plt.tight_layout()
        plt.savefig(base_mr + "_binary.png", dpi=300, bbox_inches="tight")
        plt.close()

        # ---------- moving-average + hysteresis smoothing of parity state ----------
        window_ms_mr = ModifiedRamsey_params["window_ms"]
        dt_ms_mr = rep_period_us * 1e-3
        window_n_mr = max(1, int(round(window_ms_mr / dt_ms_mr)))

        low_thresh_mr = ModifiedRamsey_params["hysteresis_low"]
        high_thresh_mr = ModifiedRamsey_params["hysteresis_high"]

        if not (0.0 <= low_thresh_mr < high_thresh_mr <= 1.0):
            raise ValueError(
                f"Invalid hysteresis thresholds: low={low_thresh_mr}, high={high_thresh_mr}"
            )

        state_avg_mr = None
        state_hyst_mr = None
        switches_hyst_mr = None
        switch_time_ms_mr = elapsed_ms_mr[1:] if len(elapsed_ms_mr) > 1 else np.array([])

        if len(binary_states_mr) >= 1:
            kernel_mr = np.ones(window_n_mr, dtype=float) / window_n_mr
            state_avg_mr = np.convolve(binary_states_mr.astype(float), kernel_mr, mode="same")

            # hysteresis state classification
            state_hyst_mr = np.empty_like(binary_states_mr)
            current_state_mr = int(binary_states_mr[0])

            for idx_mr, val_mr in enumerate(state_avg_mr):
                if val_mr >= high_thresh_mr:
                    current_state_mr = 1
                elif val_mr <= low_thresh_mr:
                    current_state_mr = 0
                state_hyst_mr[idx_mr] = current_state_mr

            switches_hyst_mr = (np.diff(state_hyst_mr) != 0).astype(int)

            # moving average trace
            plt.figure(figsize=(10, 4))
            plt.plot(elapsed_ms_mr, state_avg_mr, linewidth=1.5, label="Moving average")
            plt.axhline(high_thresh_mr, linestyle="--", linewidth=1.2,
                        label=f"High threshold = {high_thresh_mr:.2f}")
            plt.axhline(low_thresh_mr, linestyle="--", linewidth=1.2,
                        label=f"Low threshold = {low_thresh_mr:.2f}")
            plt.xlabel("Time since start (ms)")
            plt.ylabel("Smoothed parity state")
            plt.ylim(-0.05, 1.05)
            plt.title(
                f"Cycle {cycle_idx_mr + 1}: Moving-average parity trace\n"
                f"window={window_n_mr * dt_ms_mr:.3f} ms, "
                f"tau={tau_us_mr:.4f} us, df={chosen_peak_sep_mr:.4f} MHz"
            )
            plt.legend()
            plt.tight_layout()
            plt.savefig(base_mr + "_state_moving_avg.png", dpi=300, bbox_inches="tight")
            plt.close()

            # cleaned hysteresis state overlaid with raw binary points
            plt.figure(figsize=(10, 4))
            plt.step(elapsed_ms_mr, state_hyst_mr, where="post", linewidth=1.5, label="Hysteresis state")
            plt.plot(elapsed_ms_mr, binary_states_mr, "o", markersize=2, alpha=0.35, label="Raw binary state")
            plt.xlabel("Time since start (ms)")
            plt.ylabel("Parity state")
            plt.yticks([0, 1])
            plt.ylim(-0.1, 1.1)
            plt.title(
                f"Cycle {cycle_idx_mr + 1}: Moving-average + hysteresis parity trace\n"
                f"low={low_thresh_mr:.2f}, high={high_thresh_mr:.2f}, "
                f"window={window_n_mr * dt_ms_mr:.3f} ms"
            )
            plt.legend()
            plt.tight_layout()
            plt.savefig(base_mr + "_state_hysteresis.png", dpi=300, bbox_inches="tight")
            plt.close()

            # jump events from cleaned state
            if len(switches_hyst_mr) >= 1:
                plt.figure(figsize=(10, 4))
                plt.step(switch_time_ms_mr, switches_hyst_mr, where="post", linewidth=1.5)
                plt.plot(switch_time_ms_mr, switches_hyst_mr, "o", markersize=2)
                plt.xlabel("Time since start (ms)")
                plt.ylabel("Jump detected")
                plt.yticks([0, 1])
                plt.ylim(-0.1, 1.1)
                plt.title(
                    f"Cycle {cycle_idx_mr + 1}: Jumps from hysteresis-cleaned parity state\n"
                    f"low={low_thresh_mr:.2f}, high={high_thresh_mr:.2f}, "
                    f"window={window_n_mr * dt_ms_mr:.3f} ms"
                )
                plt.tight_layout()
                plt.savefig(base_mr + "_state_hysteresis_jumps.png", dpi=300, bbox_inches="tight")
                plt.close()

        np.savez(
            base_mr + ".npz",
            elapsed_ms=np.array(elapsed_ms_mr),
            raw_i=np.array(raw_i_mr),
            raw_q=np.array(raw_q_mr),
            scores=np.array(scores_mr),
            binary_states=np.array(binary_states_mr),
            state_avg=np.array(state_avg_mr) if state_avg_mr is not None else np.array([]),
            state_hysteresis=np.array(state_hyst_mr) if state_hyst_mr is not None else np.array([]),
            hysteresis_switches=np.array(switches_hyst_mr) if switches_hyst_mr is not None else np.array([]),
            switch_time_ms=np.array(switch_time_ms_mr),
            centers=np.array([c0_mr, c1_mr]),
            midpoint=np.array(midpoint_mr),
            normal=np.array(normal_mr),
            chosen_probe_freq=np.array(chosen_probe_freq_mr),
            peak_sep=np.array(chosen_peak_sep_mr),
            tau_us=np.array(tau_us_mr),
            final_voltage=np.array(current_voltage_mr),
            cycle_idx=np.array(cycle_idx_mr),
            hysteresis_low=np.array(low_thresh_mr),
            hysteresis_high=np.array(high_thresh_mr),
            moving_avg_window_n=np.array(window_n_mr),
            moving_avg_window_ms=np.array(window_n_mr * dt_ms_mr),
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

    df_required_mrc  = ModifiedRamsey_Control_params["df"]
    dV_mrc           = ModifiedRamsey_Control_params["dV"]
    voltage_min_mrc  = max(0.0, ModifiedRamsey_Control_params["voltage_min"])
    voltage_max_mrc  = ModifiedRamsey_Control_params["voltage_max"]
    max_tries_mrc    = ModifiedRamsey_Control_params["max_voltage_tries"]
    num_cycles_mrc   = ModifiedRamsey_Control_params["num_cycles"]
    half_period_v_mrc = ModifiedRamsey_Control_params["cd_period_mv"] * 1e-3 / 2.0
    sweet_max_df_mrc = ModifiedRamsey_Control_params["sweet_spot_max_df_mhz"]

    ModifiedRamsey_Control_params.setdefault("hysteresis_low",  0.4)
    ModifiedRamsey_Control_params.setdefault("hysteresis_high", 0.6)
    ModifiedRamsey_Control_params.setdefault("window_ms",       0.1)

    current_voltage_mrc = float(yoko.query(":SOUR:LEV?"))
    direction_mrc = +1
    cycle_summary_mrc = []

    # helper: run a single two-tone spec at the current voltage and return
    # (x_pts, avgi, avgq, avgamp0, peak_info, save_base)
    def _run_twotone_mrc(label, attempt_global, voltage):
        config["current_voltage"] = voltage
        config["reps"]        = ModifiedRamsey_Control_params["reps"]
        config["rounds"]      = ModifiedRamsey_Control_params["rounds"]
        config["Gauss"]       = ModifiedRamsey_Control_params["Gauss"]
        config["relax_delay"] = ModifiedRamsey_Control_params["relax_delay"]
        if config["Gauss"]:
            config["sigma"]      = ModifiedRamsey_Control_params["sigma"]
            config["qubit_gain"] = ModifiedRamsey_Control_params["gain"]
        config["qubit_length"]  = ModifiedRamsey_Control_params["qubit_length"]
        config["SpecSpan"]      = ModifiedRamsey_Control_params["SpecSpan"]
        config["SpecNumPoints"] = ModifiedRamsey_Control_params["SpecNumPoints"]
        config["step"]  = 2 * config["SpecSpan"] / config["SpecNumPoints"]
        config["start"] = qubit_frequency_center - config["SpecSpan"]
        config["expts"] = config["SpecNumPoints"]

        inst = QubitSpecSliceFF(
            path="ModifiedRamsey_Control",
            cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder
        )
        data = QubitSpecSliceFF.acquire(inst)
        QubitSpecSliceFF.save_data(inst, data)
        QubitSpecSliceFF.save_config(inst)

        xp  = np.array(data["data"]["x_pts"])
        avi = np.array(data["data"]["avgi"][0][0])
        avq = np.array(data["data"]["avgq"][0][0])
        amp = np.abs(avi + 1j * avq) ** 2
        pki = find_two_tone_peaks(xp, amp, min_sep_mhz=0.1)

        sb = save_two_tone_plot(
            x_pts=xp, avgi=avi, avgq=avq, avgamp0=amp,
            peak_info=pki, current_voltage=voltage,
            attempt_idx=attempt_global, save_dir=save_dir_mrc
        )
        return xp, avi, avq, amp, pki, sb

    for cycle_idx_mrc in range(num_cycles_mrc):
        print(f"\n================ ModifiedRamsey_Control Cycle {cycle_idx_mrc + 1}/{num_cycles_mrc} ================")

        # ------------------------------------------------------------------ #
        # STEP 1 – voltage search for V1 where separation >= df_required     #
        # ------------------------------------------------------------------ #
        V1_mrc       = None
        S1_mrc       = None
        f_ge_v1_mrc  = None
        pki_v1_mrc   = None
        success_v1   = False

        for attempt_idx_mrc in range(max_tries_mrc):
            print(
                f"[MRC] Cycle {cycle_idx_mrc + 1}, attempt {attempt_idx_mrc + 1}, "
                f"V={current_voltage_mrc:.6f} V"
            )
            global_attempt = attempt_idx_mrc + cycle_idx_mrc * max_tries_mrc
            xp, avi, avq, amp, pki, sb = _run_twotone_mrc(
                "V1_search", global_attempt, current_voltage_mrc
            )

            with open(sb + "_summary.txt", "w") as fh:
                fh.write(f"stage: V1_search\ncycle_idx: {cycle_idx_mrc}\n"
                         f"attempt_idx: {attempt_idx_mrc}\n"
                         f"current_voltage: {current_voltage_mrc:.9f}\n"
                         f"peak_freqs: {pki['peak_freqs']}\n"
                         f"peak_sep: {pki['peak_sep']}\n"
                         f"df_required: {df_required_mrc}\n")

            if pki["peak_sep"] is not None and pki["peak_sep"] >= df_required_mrc:
                V1_mrc      = current_voltage_mrc
                S1_mrc      = float(pki["peak_sep"])
                f_ge_v1_mrc = float(np.max(pki["peak_freqs"]))
                pki_v1_mrc  = pki
                print(
                    f"[MRC] V1 found: V={V1_mrc:.6f} V, "
                    f"sep={S1_mrc:.6f} MHz, f_ge={f_ge_v1_mrc:.6f} MHz"
                )
                success_v1 = True
                break

            nv, direction_mrc = choose_next_voltage(
                current_v=current_voltage_mrc, dv=dV_mrc,
                vmin=voltage_min_mrc, vmax=voltage_max_mrc, direction=direction_mrc
            )
            if abs(nv - current_voltage_mrc) < 1e-15:
                print("[MRC] Voltage search stalled at bounds.")
                break
            ramp_to(yoko, nv)
            current_voltage_mrc = nv

        if not success_v1:
            print(f"[MRC] Cycle {cycle_idx_mrc + 1}: failed to find V1.")
            cycle_summary_mrc.append({
                "cycle_idx": cycle_idx_mrc, "success": False,
                "stage_failed": "V1_search", "final_voltage": current_voltage_mrc,
            })
            continue

        # tau is derived from S1 (so it matches what ModifiedRamsey would use at V1)
        tau_mrc = 1.0 / (2.0 * S1_mrc)

        # ------------------------------------------------------------------ #
        # STEP 2 – move by T/2 and measure S2                                #
        # ------------------------------------------------------------------ #
        V2_mrc = V1_mrc + half_period_v_mrc
        if V2_mrc > voltage_max_mrc:
            V2_mrc = V1_mrc - half_period_v_mrc
        V2_mrc = float(np.clip(V2_mrc, voltage_min_mrc, voltage_max_mrc))

        ramp_to(yoko, V2_mrc)
        current_voltage_mrc = V2_mrc
        global_attempt_v2 = max_tries_mrc * cycle_idx_mrc + max_tries_mrc  # offset

        print(f"[MRC] Measuring at V2={V2_mrc:.6f} V (= V1 + T/2)")
        xp2, avi2, avq2, amp2, pki2, sb2 = _run_twotone_mrc(
            "V2_halfperiod", global_attempt_v2, V2_mrc
        )
        S2_mrc = float(pki2["peak_sep"]) if pki2["peak_sep"] is not None else 0.0

        with open(sb2 + "_summary.txt", "w") as fh:
            fh.write(f"stage: V2_halfperiod\ncycle_idx: {cycle_idx_mrc}\n"
                     f"V1: {V1_mrc:.9f}\nV2: {V2_mrc:.9f}\n"
                     f"S1_mhz: {S1_mrc:.6f}\nS2_mhz: {S2_mrc:.6f}\n"
                     f"peak_freqs: {pki2['peak_freqs']}\npeak_sep: {pki2['peak_sep']}\n")

        print(f"[MRC] V2 sep={S2_mrc:.6f} MHz")

        # ------------------------------------------------------------------ #
        # STEP 3 – interpolate sweet-spot voltage                             #
        # Physical model: separation(V) ∝ |cos(2π*(V-V0)/T)|.               #
        # V1 is near a maximum (S1 large) and V2 = V1+T/2 is the NEXT       #
        # maximum (same |cos|, opposite sign in the signed sense).           #
        # Linear interpolation treating S1 as +ve and S2 as –ve gives the   #
        # zero crossing: V_sweet = V1 + (T/2)*S1/(S1+S2).                  #
        # When S1 = S2 this yields V1 + T/4 (midpoint), which is exact if   #
        # V1 is exactly at the maximum.  The correction for off-maximum V1  #
        # is built in automatically.                                         #
        # ------------------------------------------------------------------ #
        denom_mrc = S1_mrc + S2_mrc
        if denom_mrc > 1e-6:
            V_sweet_mrc = V1_mrc + half_period_v_mrc * S1_mrc / denom_mrc
        else:
            V_sweet_mrc = V1_mrc + half_period_v_mrc / 2.0   # fallback: midpoint
        V_sweet_mrc = float(np.clip(V_sweet_mrc, voltage_min_mrc, voltage_max_mrc))

        print(
            f"[MRC] Sweet-spot estimate: V_sweet={V_sweet_mrc:.6f} V  "
            f"(S1={S1_mrc:.4f} MHz, S2={S2_mrc:.4f} MHz, "
            f"T/2={half_period_v_mrc*1e3:.4f} mV)"
        )

        # ------------------------------------------------------------------ #
        # STEP 4 – move to V_sweet and verify the two-tone                   #
        # Expected: one peak (merged), or two peaks with small separation.   #
        # ------------------------------------------------------------------ #
        ramp_to(yoko, V_sweet_mrc)
        current_voltage_mrc = V_sweet_mrc
        global_attempt_sweet = global_attempt_v2 + 1

        print(f"[MRC] Verifying sweet spot at V_sweet={V_sweet_mrc:.6f} V")
        xp_sw, avi_sw, avq_sw, amp_sw, pki_sw, sb_sw = _run_twotone_mrc(
            "sweet_spot", global_attempt_sweet, V_sweet_mrc
        )

        # Sweet-spot criterion: at zero charge dispersion the two qubit frequencies
        # merge into a single spectral peak.  verified = True only when exactly
        # one peak is found.  Two peaks (even close ones) mean the qubit is still
        # split and we are not at the sweet spot.
        num_peaks_sweet = len(pki_sw["peak_freqs"])
        S_sweet_mrc = float(pki_sw["peak_sep"]) if pki_sw["peak_sep"] is not None else 0.0
        sweet_verified = (num_peaks_sweet == 1)

        # f_ge for the Ramsey: use the single merged peak; if somehow 2 peaks were
        # found average them; if no peak at all fall back to f_ge from V1.
        if num_peaks_sweet == 1:
            f_ge_mrc = float(pki_sw["peak_freqs"][0])
        elif num_peaks_sweet == 2:
            f_ge_mrc = float(np.mean(pki_sw["peak_freqs"]))
        else:
            f_ge_mrc = f_ge_v1_mrc   # no peaks at sweet spot → use V1 frequency

        with open(sb_sw + "_summary.txt", "w") as fh:
            fh.write(f"stage: sweet_spot_verification\ncycle_idx: {cycle_idx_mrc}\n"
                     f"V_sweet: {V_sweet_mrc:.9f}\n"
                     f"num_peaks: {num_peaks_sweet}\n"
                     f"S_sweet_mhz: {S_sweet_mrc:.6f}\n"
                     f"sweet_verified: {sweet_verified}\n"
                     f"verification_criterion: exactly_1_peak\n"
                     f"f_ge_for_ramsey: {f_ge_mrc:.6f}\n"
                     f"peak_freqs: {pki_sw['peak_freqs']}\n")

        print(
            f"[MRC] Sweet-spot: {num_peaks_sweet} peak(s) found, "
            f"sep={S_sweet_mrc:.6f} MHz, verified={sweet_verified} "
            f"(need 1 merged peak), f_ge={f_ge_mrc:.6f} MHz"
        )

        # annotate the sweet-spot two-tone plot with the interpolation context
        timestamp_sw = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        base_sw_annotated = os.path.join(
            save_dir_mrc, f"Cycle_{cycle_idx_mrc:03d}_SweetSpot_{timestamp_sw}"
        )
        fig_sw, axes_sw = plt.subplots(1, 2, figsize=(14, 5))
        # left: V1 spectrum
        axes_sw[0].plot(
            np.array(xp)   if pki_v1_mrc else [],
            np.array(amp)  if pki_v1_mrc else [], ".-", label="V1"
        )
        for freq_v1 in (pki_v1_mrc["peak_freqs"] if pki_v1_mrc else []):
            axes_sw[0].axvline(freq_v1, linestyle="--",
                               label=f"{freq_v1:.4f} MHz")
        axes_sw[0].set_xlabel("Frequency (MHz)")
        axes_sw[0].set_ylabel("a.u.")
        axes_sw[0].set_title(f"V1={V1_mrc:.6f} V, sep={S1_mrc:.4f} MHz")
        axes_sw[0].legend(fontsize=8)
        # right: V_sweet spectrum
        axes_sw[1].plot(xp_sw, amp_sw, ".-", label="V_sweet")
        for freq_sw in pki_sw["peak_freqs"]:
            axes_sw[1].axvline(freq_sw, linestyle="--",
                               label=f"{freq_sw:.4f} MHz")
        axes_sw[1].set_xlabel("Frequency (MHz)")
        axes_sw[1].set_title(
            f"V_sweet={V_sweet_mrc:.6f} V, {num_peaks_sweet} peak(s), "
            f"sep={S_sweet_mrc:.4f} MHz\n"
            f"verified={sweet_verified} (need 1 merged peak)"
        )
        axes_sw[1].legend(fontsize=8)
        fig_sw.suptitle(
            f"Cycle {cycle_idx_mrc + 1}: V1 vs Sweet Spot\n"
            f"interpolation: V_sweet = V1 + (T/2)*S1/(S1+S2) = {V_sweet_mrc:.6f} V"
        )
        plt.tight_layout()
        plt.savefig(base_sw_annotated + "_comparison.png", dpi=300, bbox_inches="tight")
        plt.close()

        # ------------------------------------------------------------------ #
        # STEP 5 – run Modified Ramsey at V_sweet (only if verified)         #
        # ------------------------------------------------------------------ #
        if sweet_verified:
            mr_cfg_mrc = {
                "f_ge":          f_ge_mrc,
                "df":            S1_mrc,       # tau = 1/(2*S1), same as ModifiedRamsey at V1
                "pi2_gain":      pi2_gain,
                "sigma":         qubit_sigma,
                "flattop_length": qubit_flattop,
                "reps":          ModifiedRamsey_Control_params["mr_reps"],
                "rounds":        1,
                "current_voltage": V_sweet_mrc,
                "Qubit_number":  Qubit_Readout,
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
                f"V_sweet={V_sweet_mrc:.6f} V, f_ge={f_ge_mrc:.6f} MHz, "
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
                elapsed_ms        = np.array(elapsed_ms_mrc),
                raw_i             = np.array(raw_i_mrc),
                raw_q             = np.array(raw_q_mrc),
                scores            = np.array(scores_mrc),
                binary_states     = np.array(binary_states_mrc),
                state_avg         = np.array(state_avg_mrc)  if state_avg_mrc  is not None else np.array([]),
                state_hysteresis  = np.array(state_hyst_mrc) if state_hyst_mrc is not None else np.array([]),
                hysteresis_switches = np.array(switches_hyst_mrc) if switches_hyst_mrc is not None else np.array([]),
                switch_time_ms    = np.array(switch_time_ms_mrc),
                centers           = np.array([c0_mrc, c1_mrc]),
                midpoint          = np.array(midpoint_mrc),
                normal            = np.array(normal_mrc),
                V1                = np.array(V1_mrc),
                V2                = np.array(V2_mrc),
                V_sweet           = np.array(V_sweet_mrc),
                S1_mhz            = np.array(S1_mrc),
                S2_mhz            = np.array(S2_mrc),
                S_sweet_mhz       = np.array(S_sweet_mrc),
                f_ge              = np.array(f_ge_mrc),
                tau_us            = np.array(tau_mrc),
                half_period_v     = np.array(half_period_v_mrc),
                cycle_idx         = np.array(cycle_idx_mrc),
                hysteresis_low    = np.array(low_thresh_mrc),
                hysteresis_high   = np.array(high_thresh_mrc),
                moving_avg_window_n  = np.array(window_n_mrc),
                moving_avg_window_ms = np.array(window_n_mrc * dt_ms_mrc),
                config            = np.array(config_mrc, dtype=object),
            )

            with open(base_mrc + "_config.json", "w") as fh:
                json.dump(config_mrc, fh, indent=2, default=float)

            cycle_summary_mrc.append({
                "cycle_idx":      cycle_idx_mrc,
                "success":        True,
                "V1":             V1_mrc,
                "V2":             V2_mrc,
                "V_sweet":        V_sweet_mrc,
                "S1_mhz":         S1_mrc,
                "S2_mhz":         S2_mrc,
                "S_sweet_mhz":    S_sweet_mrc,
                "sweet_verified": True,
                "f_ge":           f_ge_mrc,
                "tau_us":         tau_mrc,
            })

        else:
            print(
                f"[MRC] Cycle {cycle_idx_mrc + 1}: sweet spot not verified "
                f"({num_peaks_sweet} peak(s) found at V_sweet={V_sweet_mrc:.6f} V; "
                f"need exactly 1 merged peak). Skipping Ramsey run."
            )
            cycle_summary_mrc.append({
                "cycle_idx":      cycle_idx_mrc,
                "success":        False,
                "stage_failed":   "sweet_spot_not_verified",
                "V1":             V1_mrc,
                "V2":             V2_mrc,
                "V_sweet":        V_sweet_mrc,
                "S1_mhz":         S1_mrc,
                "S2_mhz":         S2_mrc,
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
        AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
        AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF_N.save_config(iAmpRabi)
    else:
        iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                   outerFolder=outerFolder)
        dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
        AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
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
        QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=False, figNum=2)
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
        QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
        QubitSpecSliceFF.save_config(Instance_specSlice)
        x_pts = np.array(data_specSlice['data']['x_pts'])
        avgi = np.array(data_specSlice['data']['avgi'][0][0])
        avgq = np.array(data_specSlice['data']['avgq'][0][0])
        sig = avgi + 1j * avgq
        avgamp0 = np.abs(sig) **2
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
            cbar.set_label("|I + iQ|^2")

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
    if config['pi2_SS']:
        config['qubit_gain'] = pi2_gain
        print(pi2_gain)
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

# ramp_to(yoko, 0.0)
# yoko.write(":OUTP OFF")
yoko.close()
###############################################`