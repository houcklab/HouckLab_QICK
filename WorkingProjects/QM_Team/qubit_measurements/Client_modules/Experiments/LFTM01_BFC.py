# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.CoreLib.socProxy import *
import time
from sklearn.cluster import KMeans
from utils import *
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleTone import SingleTone

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF import AmplitudeRabiFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChiShift import ChiShift

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1_SS import T1_SS
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleQubitRB import SingleQubitRB
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2CPMG import T2ECPMG
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChargeDispersionQuasiCW import ChargeDispersionQuasiCW
from datetime import datetime
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mModifiedRamsey import ModifiedRamsey

from datetime import datetime, timedelta
import matplotlib.dates as mdates

# from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
# from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift
# from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF import SingleShotProgramFF
# from q4diamond.Client_modules.Experiment_Scripts.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF

soc, soccfg = makeProxy()

##############LFTM01 (with charge line set up) ############################
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 4700.411180, 'Gain': 500}, # 510 slightly too much 540 too much 690 okay for high distinguishing
          'Qubit': {'Frequency': 1263.042764, 'Gain': 7375,'pi2_Gain' : 7375 // 2, "sigma": 1, "flattop_length": None}, # qubit found again previous frequency 1263.228
          'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/LFTM01/RFSOC/Q1//"},# 2840
    '2': {'Readout': {'Frequency': 4909.553, 'Gain': 168}, # 180 is slightly too much 170 used for normal
          'Qubit': {'Frequency':  1144.79, 'Gain': 326, 'pi2_Gain' : 326 // 2, "sigma": 1, "flattop_length": None}, # pi pulse gain: 4164
          'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/LFTM01/RFSOC/Q2//"},
    }
# ############## End Can D ############################

############## New TATQ03 (No Charge Lines) ############################
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 4700.262734, 'Gain': 2150}, #1400 maybe too much, 1500 probably too much, 1920 too much 1200 good, mist at 2500
#           'Qubit': {'Frequency': 1263.058, 'Gain': 6120,'pi2_Gain' : 6120 // 2, "sigma": 0.8, "flattop_length": None}, # qubit found again previous frequency 1263.228 6057
#           'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/LFTM01/RFSOC/Q1//"},# 2840
#     '2': {'Readout': {'Frequency':4909.557590, 'Gain': 550}, # 450 too much # 400 used for no mist in initial readout
#           'Qubit': {'Frequency': 1144.78552, 'Gain': 2333, 'pi2_Gain' : 2333 // 2, "sigma": 0.8, "flattop_length": None}, # pi pulse gain: 4164
#           'outerfoldername':"V:/t1Team/Data/2026-3-9_BFC_Cooldown/LFTM01/RFSOC/Q2//"},
#     }
############## End Can D ############################


# Readout
Qubit_Readout = 2
Qubit_Pulse = 2
outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

ConstantTone = False  # determine cavity frequency

RunTransmissionSweep = False # determine cavity frequency
Run2ToneSpec =  False
RunTrans_QubitSpec = False
Spec_relevant_params = {"qubit_gain": 1, "SpecSpan": .1, "SpecNumPoints": 101,
                        'qubit_length' : 30,
                        "reps": 10, 'rounds': 10,
                        'Gauss': True, "sigma": 2, "gain": 5,
                        "display": True, 'relax_delay' : 3000,
                        } # False -- no pulse #If you don't see RabiAmp but with Gauss True see the qubit, the next thing to check is gain, you might not have the right pi pulse


Run2ToneChargeDispersionQuasiCW = False
TwoToneChargeDispersion_params = {
    "df": 0.01,                 # required peak separation in MHz
    "max_tries": 1000,    # max search steps per cycle
    "num_cycles": 1000,           # how many times to repeat: search -> quasiCW -> restart
    "use_upper_peak": True,     # True -> probe higher-frequency peak, False -> lower-frequency peak

    # two-tone spec settings used during the search
    "SpecSpan": 0.3,
    "SpecNumPoints": 101,
    "reps": 10,
    "rounds": 10,
    "relax_delay": 500,
    "Gauss": False,
    "sigma": 2,
    "gain": 450,
    "qubit_length": 100,

    # quasi-CW settings once the peaks are separated enough
    "qcw_repetitions": 500,
    "qcw_relax_delay": 1000,
}

RunModifiedRamsey = False
ModifiedRamsey_params = {
    "df": 0.01,               # required two-peak separation in MHz before Ramsey runs
    "max_tries": 1000,        # max repeated two-tone attempts per cycle
    "num_cycles": 1000,       # repeat: search -> ModifiedRamsey -> restart

    # which peak to lock to for f_ge
    # True = use upper-frequency peak, False = use lower-frequency peak
    "use_upper_peak": True,

    # two-tone spec settings used during the search
    "SpecSpan": 0.3,
    "SpecNumPoints": 101,
    "reps": 10,
    "rounds": 10,
    "relax_delay": 4500,
    "Gauss": False,
    "sigma": 2,
    "gain": 450,
    "qubit_length": 100,

    # Modified Ramsey settings once peaks are resolved
    "mr_reps": 2500,           # number of repeated single-shot Ramsey measurements
    "mr_plot": False,
}


RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "max_gain": 650, 'number_of_steps': 101,
                         "reps": 15, 'rounds': 15,
                         'relax_delay': 4500,
                         'fit' : True}  #Always change the max gain if you don't see it, also compare what you get with Transmission data
# 15000 for Q1, 2800 for Q2

RunChiShift = False # Q1 chi shift: -0.198020 MHz (now measured to be .238 MHZ) Q2 chi shift:  -0.158416
ChiShift_params = {"reps": 10,
                    'rounds': 10,# this will used for all experiements below unless otherwise changed in between trials
                    "TransSpan": 1,  ### MHz, span will be center+/- this parameter
                    "TransNumPoints": 101,
                    "cavity_shift": 0.0,
                    "relax_delay": 5000}

RunT1 = False
RunT2 = True
T1T2_params = {"T1_step": 70, "T1_expts": 60, "T1_reps": 20, "T1_rounds": 20, # 80 100 30 30
               "T2_step": 9, "T2_expts": 125, "T2_reps": 20, "T2_rounds": 20, "freq_shift": 0.0, # 2.5 250 for Q1
               "relax_delay": 4500,
               'repetitions': 3000}

RunAllQubits_T1 = False

RunT1T2E = False

RunT1T2RT2E = False

RunT2E = False
T2E_params = {"T2_max_us": 2000, "T2_expts": 101, "T2_reps": 25, "T2_rounds": 25, "freq_shift": 0.0,
               "relax_delay": 5000, 'num_pi_pulses': 1, #need odd number of pulses
              "rotation_angle": None,
              "min_max": None,
              'repetitions': 3000}

RunT2CPMG = False
T2CPMG_params = {"T2_max_us": 1500, "T2_expts": 50, "T2_reps": 20, "T2_rounds": 50, "freq_shift": 0.0,
               "relax_delay": 4500,#need odd number of pulses
              'repetitions': 1000,
              "num_pulses": [3, 5, 7, 9, 11],
              'T2_max_us_list': [1500, 1500, 1500, 1500, 1500],
                # 'T2_max_us_list': [600, 800, 1000, 1200, 1300, 1500, 1600] #1000, 1500, 1700, 2000, 2000, 2000],
                 }

RunAllQubits_T1T2T2E = False

AllQubit_T1T2T2E_params = {
    "T1_step": 60,
    "T1_expts": 60,
    "T1_reps": 25,
    "T1_rounds": 25,

    "T2_step": 2.5,
    "T2_expts": 300,
    "T2_reps": 25,
    "T2_rounds": 25,
    "T2_freq_shift": 0.0,

    "T2E_max_us": 2500,
    "T2E_expts": 101,
    "T2E_reps": 30,
    "T2E_rounds": 30,
    "T2E_freq_shift": 0.0,
    "T2E_num_pi_pulses": 1,
    "T2E_rotation_angle": None,
    "T2E_min_max": None,

    "relax_delay": 4500,
    "sleep_between_experiments": 0.5,
    "repetitions": 3000,
}

RunRB = False
RB_params = {
    "rb_lengths": [1, 2, 4,], # 8, 16, 32,],#  64, 96, 128],
    "rb_nseeds": 20,
    "rb_seed": 1234,
    "reps": 10,
    "rounds": 10,
    "relax_delay": 4500,
}

SingleShot = True
SS_params = {"Shots": 1000, "Readout_Time": 20, "ADC_Offset": 1, "Qubit_Pulse": [Qubit_Pulse],
             'number_of_pulses': 1, 'relax_delay': 4500, "pi2_SS": False}

RunT1SS = False
T1SS_params = {"T1_step": 80, "T1_expts": 100,
               "reps": 2000,
               'angle': 0, 'threshold': 0,
               "relax_delay": 8000,
               'calibrate_SS': True,
               'repetitions': 11}



SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 100, "gain_stop": 200, "gain_pts": 11, "span": 0.1, "trans_pts": 11} # started seeing MIST around 2675 2400

SingleShot_QubitOptimize = False
SS_Q_params = {"q_gain_span": 20, "q_gain_pts": 21, "q_freq_span": 0.1, "q_freq_pts": 21,
               'number_of_pulses': 1} # for optimizing pi/2 pulse, set the gain to the half of its value and optimize for n=2


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
    "readout_length": 30,  # 15 [us]
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
    "qubit_length": 100, # 20, 100
    "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
}
expt_cfg = {
    "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
    "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
    "expts": qubit_config["SpecNumPoints"]
}

UpdateConfig = trans_config | qubit_config | expt_cfg
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits
config["Qubit_number"] = Qubit_Pulse

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

if ConstantTone:
    Instance_trans = SingleTone(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = SingleTone.acquire(Instance_trans)

cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak

# perform the cavity transmission experiment
if RunTransmissionSweep:

    # -------------------- acquire transmission --------------------
    config["reps"] = 20
    config["rounds"] = 20

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
    display = Spec_relevant_params['display']

    Instance_specSlice = QubitSpecSliceFF(
        path="QubitSpecFF",
        cfg=config,
        soc=soc,
        soccfg=soccfg,
        outerFolder=outerFolder
    )
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=display, figNum=2) # can change to True
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
        AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2, fit=Amplitude_Rabi_params["fit"])
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
        # sanity_dump(config)
        # config["reps"] = 20  # fast axis number of points
        # config["rounds"] = 20  # slow axis number of points
        # Instance_trans = CavitySpecFF(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
        #                               outerFolder=outerFolder)
        # data_trans = CavitySpecFF.acquire(Instance_trans)
        # CavitySpecFF.display(Instance_trans, data_trans, plotDisp=False, figNum=1)
        # CavitySpecFF.save_data(Instance_trans, data_trans)
        # CavitySpecFF.save_config(Instance_trans)
        #
        # # update the transmission frequency to be the peak
        # if cavity_min:
        #     config["pulse_freq"] = Instance_trans.peakFreq_min
        # else:
        #     config["pulse_freq"] = Instance_trans.peakFreq_max
        # print("Cavity frequency found at: ", config["pulse_freq"])

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



#######################################################
qubit_gains = [Qubit_Parameters[str(Q_R)]['Qubit']['Gain'] for Q_R in SS_params["Qubit_Pulse"]]
qubit_frequency_centers = [Qubit_Parameters[str(Q_R)]['Qubit']['Frequency'] for Q_R in SS_params["Qubit_Pulse"]]


UpdateConfig = {
    ###### cavity
    # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "read_pulse_style": "const", # --Fixed
    "readout_length": SS_params["Readout_Time"], # us (length of the pulse applied)
    "adc_trig_offset": SS_params["ADC_Offset"],
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
        "trans_freq_start": config["pulse_freq"] - span / 2, #249.6,
        "trans_freq_stop": config["pulse_freq"] + span / 2, #250.3,
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
    Qubit_Pulse_Index = 0
    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": max([0, int(qubit_gains[Qubit_Pulse_Index] - int(q_gain_span))]), # - q_gain_span / 2,
        "qubit_gain_Stop":  min([32767, int(qubit_gains[Qubit_Pulse_Index] + int(q_gain_span))]),# *qubit_gains[Qubit_Pulse_Index] + q_gain_span / 2,
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

    QubitPulseOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)

###############################################

if RunRB:
    rb_cfg = {
        "reps": RB_params["reps"],
        "rounds": RB_params["rounds"],
        "pi_gain": qubit_gain,
        "pi2_gain": pi2_gain,
        "relax_delay": RB_params["relax_delay"],
        "f_ge": qubit_frequency_center,
        "sigma": qubit_sigma,
        "flattop_length": qubit_flattop,
        "rb_lengths": RB_params["rb_lengths"],
        "rb_nseeds": RB_params["rb_nseeds"],
        "rb_seed": RB_params["rb_seed"],
    }

    config_rb = config | rb_cfg
    iRB = SingleQubitRB(path="RB", cfg=config_rb, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dRB = SingleQubitRB.acquire(iRB)
    SingleQubitRB.display(iRB, dRB, plotDisp=True, figNum=7)
    SingleQubitRB.save_data(iRB, dRB)
    SingleQubitRB.save_config(iRB)

def make_qubit_base_config(q_idx):
    q = Qubit_Parameters[str(q_idx)]

    cavity_gain = q["Readout"]["Gain"]
    resonator_frequency_center = q["Readout"]["Frequency"]
    qubit_gain = q["Qubit"]["Gain"]
    pi2_gain = q["Qubit"]["pi2_Gain"]
    qubit_frequency_center = q["Qubit"]["Frequency"]
    qubit_sigma = q["Qubit"]["sigma"]
    qubit_flattop = q["Qubit"]["flattop_length"]
    outerFolder = q["outerfoldername"]

    trans_config = {
        "reps": 1000,
        "pulse_style": "const",
        "readout_length": 30,
        "pulse_gain": cavity_gain,
        "pulse_freq": resonator_frequency_center,
        "TransSpan": 0.75,
        "TransNumPoints": 301,
        "cav_relax_delay": 30,
    }

    qubit_config = {
        "qubit_pulse_style": "const",
        "qubit_gain": 25,
        "qubit_freq": qubit_frequency_center,
        "qubit_length": 100,
        "SpecSpan": 0.05,
        "SpecNumPoints": 101,
    }

    expt_cfg = {
        "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
        "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
        "expts": qubit_config["SpecNumPoints"],
    }

    cfg = BaseConfig | trans_config | qubit_config | expt_cfg
    cfg["FF_Qubits"] = FF_Qubits
    cfg["cavity_min"] = True

    return {
        "config": cfg,
        "outerFolder": outerFolder,
        "qubit_gain": qubit_gain,
        "pi2_gain": pi2_gain,
        "qubit_frequency_center": qubit_frequency_center,
        "qubit_sigma": qubit_sigma,
        "qubit_flattop": qubit_flattop,
    }


if RunAllQubits_T1T2T2E:
    for i in range(AllQubit_T1T2T2E_params["T1_step"]):
        for q_idx in sorted(Qubit_Parameters.keys(), key=int):
            qinfo = make_qubit_base_config(q_idx)
            config_q = qinfo["config"]
            outerFolder_q = qinfo["outerFolder"]

            print(f"\n=== Running T1/T2R/T2E for qubit {q_idx} ===")

            # -------------------- T1 --------------------
            cfg_t1 = config_q | {
                "start": 0,
                "step": AllQubit_T1T2T2E_params["T1_step"],
                "expts": AllQubit_T1T2T2E_params["T1_expts"],
                "reps": AllQubit_T1T2T2E_params["T1_reps"],
                "rounds": AllQubit_T1T2T2E_params["T1_rounds"],
                "Qubit_number": int(q_idx),
                "pi_gain": qinfo["qubit_gain"],
                "relax_delay": AllQubit_T1T2T2E_params["relax_delay"],
                "sigma": qinfo["qubit_sigma"],
                "flattop_length": qinfo["qubit_flattop"],
                "f_ge": qinfo["qubit_frequency_center"],
            }
            iT1 = T1FF(path=f"T1_Q{q_idx}", cfg=cfg_t1, soc=soc, soccfg=soccfg, outerFolder=outerFolder_q)
            dT1 = T1FF.acquire(iT1)
            T1FF.display(iT1, dT1, plotDisp=False, figNum=400 + int(q_idx))
            T1FF.save_data(iT1, dT1)
            T1FF.save_config(iT1)
            time.sleep(AllQubit_T1T2T2E_params["sleep_between_experiments"])
            soc.reset_gens()

            # -------------------- T2R --------------------
            cfg_t2 = config_q | {
                "start": 0,
                "step": AllQubit_T1T2T2E_params["T2_step"],
                "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
                "expts": AllQubit_T1T2T2E_params["T2_expts"],
                "reps": AllQubit_T1T2T2E_params["T2_reps"],
                "rounds": AllQubit_T1T2T2E_params["T2_rounds"],
                "Qubit_number": int(q_idx),
                "pi_gain": qinfo["qubit_gain"],
                "pi2_gain": qinfo["pi2_gain"],
                "relax_delay": AllQubit_T1T2T2E_params["relax_delay"],
                "f_ge": qinfo["qubit_frequency_center"] + AllQubit_T1T2T2E_params["T2_freq_shift"],
                "sigma": qinfo["qubit_sigma"],
                "flattop_length": qinfo["qubit_flattop"],
            }
            iT2R = T2R(path=f"T2R_Q{q_idx}", cfg=cfg_t2, soc=soc, soccfg=soccfg, outerFolder=outerFolder_q)
            dT2R = T2R.acquire(iT2R)
            T2R.display(iT2R, dT2R, plotDisp=False, figNum=500 + int(q_idx))
            T2R.save_data(iT2R, dT2R)
            T2R.save_config(iT2R)
            time.sleep(AllQubit_T1T2T2E_params["sleep_between_experiments"])
            soc.reset_gens()

            # -------------------- T2E --------------------
            num_pulses = AllQubit_T1T2T2E_params["T2E_num_pi_pulses"]
            int_steps = AllQubit_T1T2T2E_params["T2E_max_us"] // (
                0.00232515 * (num_pulses + 1) * AllQubit_T1T2T2E_params["T2E_expts"]
            )

            if int_steps == 0:
                print(f"[T2E] Step size is 0 for qubit {q_idx}, skipping T2E.")
                continue

            cfg_t2e = config_q | {
                "start": 0,
                "step": 0.00232515 * (num_pulses + 1) * int_steps,
                "expts": AllQubit_T1T2T2E_params["T2E_expts"],
                "reps": AllQubit_T1T2T2E_params["T2E_reps"],
                "rounds": AllQubit_T1T2T2E_params["T2E_rounds"],
                "Qubit_number": int(q_idx),
                "pi_gain": qinfo["qubit_gain"],
                "pi2_gain": qinfo["pi2_gain"],
                "relax_delay": AllQubit_T1T2T2E_params["relax_delay"],
                "f_ge": qinfo["qubit_frequency_center"] + AllQubit_T1T2T2E_params["T2E_freq_shift"],
                "num_pi_pulses": num_pulses,
                "sigma": qinfo["qubit_sigma"],
                "flattop_length": qinfo["qubit_flattop"],
            }

            if AllQubit_T1T2T2E_params["T2E_rotation_angle"] is not None:
                cfg_t2e["rotation_angle"] = AllQubit_T1T2T2E_params["T2E_rotation_angle"]
                cfg_t2e["min_max"] = AllQubit_T1T2T2E_params["T2E_min_max"]

            iT2E = T2EMUX(path=f"T2E_Q{q_idx}", cfg=cfg_t2e, soc=soc, soccfg=soccfg, outerFolder=outerFolder_q)
            dT2E = T2EMUX.acquire(iT2E)
            T2EMUX.display(iT2E, dT2E, plotDisp=False, figNum=600 + int(q_idx))
            T2EMUX.save_data(iT2E, dT2E)
            T2EMUX.save_config(iT2E)
            time.sleep(AllQubit_T1T2T2E_params["sleep_between_experiments"])
            soc.reset_gens()

if RunAllQubits_T1:
    # ---------- Alternating T1 on Q1 and Q2 ----------

    num_cycles = 1000  # how many times to alternate
    sleep_between = 5  # seconds between runs

    for cycle in range(num_cycles):
        print(f"\n===== Cycle {cycle + 1}/{num_cycles} =====")

        for q_idx in ['1', '2']:  # alternate Q1 -> Q2
            qinfo = make_qubit_base_config(q_idx)
            config_q = qinfo["config"]
            outerFolder_q = qinfo["outerFolder"]

            print(f"\n--- Running T1 on Q{q_idx} ---")

            cfg_t1 = config_q | {
                "start": 0,
                "step": T1T2_params["T1_step"],
                "expts": T1T2_params["T1_expts"],
                "reps": T1T2_params["T1_reps"],
                "rounds": T1T2_params["T1_rounds"],
                "Qubit_number": int(q_idx),

                "pi_gain": qinfo["qubit_gain"],
                "relax_delay": T1T2_params["relax_delay"],
                "sigma": qinfo["qubit_sigma"],
                "flattop_length": qinfo["qubit_flattop"],
                "f_ge": qinfo["qubit_frequency_center"],
            }

            iT1 = T1FF(
                path=f"T1_Q{q_idx}",
                cfg=cfg_t1,
                soc=soc,
                soccfg=soccfg,
                outerFolder=outerFolder_q
            )

            dT1 = T1FF.acquire(iT1)
            T1FF.display(iT1, dT1, plotDisp=False, figNum=100 + int(q_idx))
            T1FF.save_data(iT1, dT1)
            T1FF.save_config(iT1)

            time.sleep(sleep_between)
            soc.reset_gens()


if RunT2CPMG:
    for r in range(T2E_params["repetitions"]):
        for ind, num_p in enumerate(T2CPMG_params["num_pulses"]):
            number_of_steps = 3
            ARabi_config = {'gain_start': 0, "gain_end": qubit_gain,
                            'gainNumPoints': number_of_steps,
                            "reps": Amplitude_Rabi_params['reps'],
                            "rounds": Amplitude_Rabi_params['rounds'],
                            "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
                            "relax_delay": 5000,
                            "flattop_length": qubit_flattop,
                            "Qubit_number" : Qubit_Pulse}
            config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
            iAmpRabi = AmplitudeRabiFF_N(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                         outerFolder=outerFolder)
            dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
            rotation_angle, min_max = AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=False, figNum=2)
            AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
            AmplitudeRabiFF_N.save_config(iAmpRabi)
            config["rotation_angle"] = rotation_angle
            config["min_max"] = min_max

            num_pulses = num_p
            if T2CPMG_params["T2_max_us_list"] != None:
                max_t2 = T2CPMG_params["T2_max_us_list"][ind]
            else:
                max_t2 = T2CPMG_params["T2_max_us"]

            if num_pulses == 0:
                int_steps = max_t2 // (0.00232515 * T2CPMG_params["T2_expts"] * 2)
                step = 0.00232515 * int_steps * 2
            else:
                int_steps = max_t2 // (0.00232515 * T2CPMG_params["T2_expts"] * num_pulses * 2)
                step = .00232515 * num_pulses * int_steps * 2
            # print(step, step / 0.00232515)
            # print(step * T2CPMG_params["T2_expts"], step / num_pulses / 2,
            #       step / num_pulses / 2  / 0.00232515)
            T2CPMG_cfg = {"start": 0, "step": step,
                       "expts": T2CPMG_params["T2_expts"], "reps": T2CPMG_params["T2_reps"],
                          "rounds": T2CPMG_params["T2_rounds"],
                       "pi_gain": qubit_gain, "sigma": qubit_sigma,
                       "pi2_gain": pi2_gain, "relax_delay": T2CPMG_params["relax_delay"],
                       'f_ge': qubit_frequency_center + T2CPMG_params["freq_shift"],
                       "num_pi_pulses": num_p,
                       "flattop_length": qubit_flattop
                       }
            if int_steps == 0:
                print('Step size is 0! need to increase total time or decrease experiments')
            else:
                config = config | T2CPMG_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
                iT2E = T2ECPMG(path="T2E", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
                dT2E = T2ECPMG.acquire(iT2E)
                T2ECPMG.display(iT2E, dT2E, plotDisp=False, figNum=2)
                T2ECPMG.save_data(iT2E, dT2E)
                T2ECPMG.save_config(iT2E)

                time.sleep(10)
                soc.reset_gens()

if Run2ToneChargeDispersionQuasiCW:
    save_dir = os.path.join(outerFolder, "TwoToneChargeDispersion")
    os.makedirs(save_dir, exist_ok=True)

    df_required = TwoToneChargeDispersion_params["df"]
    max_tries = TwoToneChargeDispersion_params["max_tries"]
    num_cycles = TwoToneChargeDispersion_params["num_cycles"]

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
                f"attempt {attempt_idx + 1}/{max_tries}"
            )

            # --- run two-tone spec ---
            config["reps"] = TwoToneChargeDispersion_params["reps"]
            config["rounds"] = TwoToneChargeDispersion_params["rounds"]
            config["Gauss"] = TwoToneChargeDispersion_params["Gauss"]
            config["relax_delay"] = TwoToneChargeDispersion_params["relax_delay"]

            if config["Gauss"]:
                config["sigma"] = TwoToneChargeDispersion_params["sigma"]

            config["qubit_gain"] = TwoToneChargeDispersion_params["gain"]
            df = TwoToneChargeDispersion_params["df"]

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

            peak_info = find_two_tone_peaks(x_pts, avgamp0, min_sep_mhz=df/2)

            save_base = save_two_tone_plot(
                x_pts=x_pts,
                avgi=avgi,
                avgq=avgq,
                avgamp0=avgamp0,
                peak_info=peak_info,
                attempt_idx=attempt_idx + cycle_idx * max_tries,
                save_dir=save_dir
            )

            with open(save_base + "_summary.txt", "w") as f:
                f.write(f"cycle_idx: {cycle_idx}\n")
                f.write(f"attempt_idx: {attempt_idx}\n")
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

        # ---------- if search failed, record and continue to next cycle ----------
        if not success:
            print(f"[TwoToneChargeDispersion] Cycle {cycle_idx + 1}: failed to find sufficient peak separation.")
            cycle_summary.append({
                "cycle_idx": cycle_idx,
                "success": False,
                "chosen_probe_freq": None,
                "peak_sep": None,
            })
            continue

        # ---------- run quasi-CW for this cycle ----------
        probe_freq = chosen_probe_freq

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
        config["start"] = probe_freq
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
            f"Cycle {cycle_idx + 1}: QuasiCW IQ, "
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
            peak_sep=np.array(chosen_peak_sep),
            cycle_idx=np.array(cycle_idx),
            config=np.array(config, dtype=object),
        )

        with open(base + "_config.json", "w") as f:
            json.dump(config, f, indent=2, default=float)

        cycle_summary.append({
            "cycle_idx": cycle_idx,
            "success": True,
            "chosen_probe_freq": chosen_probe_freq,
            "peak_sep": chosen_peak_sep,
        })

        # after finishing this cycle, restart the search

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
    max_tries_mr = ModifiedRamsey_params["max_tries"]
    num_cycles_mr = ModifiedRamsey_params["num_cycles"]

    cycle_summary_mr = []

    for cycle_idx_mr in range(num_cycles_mr):
        print(
            f"\n================ ModifiedRamsey Cycle "
            f"{cycle_idx_mr + 1}/{num_cycles_mr} ================"
        )

        success_mr = False
        chosen_probe_freq_mr = None
        chosen_peak_sep_mr = None
        chosen_peak_freqs_mr = None

        # ---------- repeated two-tone search at fixed device conditions ----------
        for attempt_idx_mr in range(max_tries_mr):
            print(
                f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}/{num_cycles_mr}, "
                f"attempt {attempt_idx_mr + 1}/{max_tries_mr}"
            )

            # --- run two-tone spec for Modified Ramsey search ---
            config["reps"] = ModifiedRamsey_params["reps"]
            config["rounds"] = ModifiedRamsey_params["rounds"]
            config["Gauss"] = ModifiedRamsey_params["Gauss"]
            config["relax_delay"] = ModifiedRamsey_params["relax_delay"]

            if config["Gauss"]:
                config["sigma"] = ModifiedRamsey_params["sigma"]

            config["qubit_gain"] = ModifiedRamsey_params["gain"]
            df_search_mr = ModifiedRamsey_params["df"]

            config["qubit_length"] = ModifiedRamsey_params["qubit_length"]
            config["SpecSpan"] = ModifiedRamsey_params["SpecSpan"]
            config["SpecNumPoints"] = ModifiedRamsey_params["SpecNumPoints"]
            config["step"] = 2 * config["SpecSpan"] / config["SpecNumPoints"]
            config["start"] = qubit_frequency_center - config["SpecSpan"]
            config["expts"] = config["SpecNumPoints"]

            Instance_specSlice_mr = QubitSpecSliceFF(
                path="ModifiedRamsey_Search",
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

            peak_info_mr = find_two_tone_peaks(
                x_pts_mr,
                avgamp0_mr,
                min_sep_mhz=df_search_mr / 2
            )

            save_base_mr = save_two_tone_plot(
                x_pts=x_pts_mr,
                avgi=avgi_mr,
                avgq=avgq_mr,
                avgamp0=avgamp0_mr,
                peak_info=peak_info_mr,
                attempt_idx=attempt_idx_mr + cycle_idx_mr * max_tries_mr,
                save_dir=save_dir_mr
            )

            with open(save_base_mr + "_summary.txt", "w") as f:
                f.write(f"cycle_idx: {cycle_idx_mr}\n")
                f.write(f"attempt_idx: {attempt_idx_mr}\n")
                f.write(f"peak_freqs: {peak_info_mr['peak_freqs']}\n")
                f.write(f"peak_vals: {peak_info_mr['peak_vals']}\n")
                f.write(f"peak_sep: {peak_info_mr['peak_sep']}\n")
                f.write(f"df_required: {df_required_mr}\n")

            if (
                peak_info_mr["peak_sep"] is not None
                and peak_info_mr["peak_sep"] >= df_required_mr
            ):
                if ModifiedRamsey_params["use_upper_peak"]:
                    chosen_probe_freq_mr = float(np.max(peak_info_mr["peak_freqs"]))
                else:
                    chosen_probe_freq_mr = float(np.min(peak_info_mr["peak_freqs"]))

                chosen_peak_sep_mr = float(peak_info_mr["peak_sep"])
                chosen_peak_freqs_mr = [float(v) for v in peak_info_mr["peak_freqs"]]

                print(
                    f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}: peaks found, "
                    f"sep={chosen_peak_sep_mr:.6f} MHz, "
                    f"f_ge={chosen_probe_freq_mr:.6f} MHz, "
                    f"tau={1.0 / (2.0 * chosen_peak_sep_mr):.6f} us"
                )
                success_mr = True
                break

        if not success_mr:
            print(
                f"[ModifiedRamsey] Cycle {cycle_idx_mr + 1}: "
                f"failed to find sufficient peak separation."
            )
            cycle_summary_mr.append({
                "cycle_idx": cycle_idx_mr,
                "success": False,
                "chosen_probe_freq": None,
                "peak_sep": None,
                "tau_us": None,
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

            # these are used by your existing readout config / base config
            "pulse_freq": config["pulse_freq"],
            "pulse_gain": config["pulse_gain"],
            "readout_length": config["readout_length"],
            "adc_trig_offset": config["adc_trig_offset"],
            "length": config["length"],

            "Qubit_number": Qubit_Pulse,
        }

        config_mr = config | mr_cfg

        iMR = ModifiedRamsey(
            path="ModifiedRamsey",
            cfg=config_mr,
            soc=soc,
            soccfg=soccfg,
            outerFolder=outerFolder
        )

        start_dt_mr = datetime.now()
        dMR = iMR.acquire()
        iMR.display(dMR, plotDisp=ModifiedRamsey_params["mr_plot"], figNum=50)
        iMR.save_data(dMR)
        iMR.save_config()

        # ------------------------------------------------------------
        # Classify each shot into 0/1 and save time-series PNGs
        # ------------------------------------------------------------
        shots_i_mr = np.asarray(dMR["data"]["shots_i"]).ravel()
        shots_q_mr = np.asarray(dMR["data"]["shots_q"]).ravel()
        iq_mr = np.column_stack([shots_i_mr, shots_q_mr])

        kmeans_mr = KMeans(n_clusters=2, random_state=0, n_init=20)
        kmeans_mr.fit(iq_mr)
        centers_mr = kmeans_mr.cluster_centers_

        c0_mr = centers_mr[0]
        c1_mr = centers_mr[1]
        normal_mr = c1_mr - c0_mr
        midpoint_mr = 0.5 * (c0_mr + c1_mr)
        scores_mr = (iq_mr - midpoint_mr) @ normal_mr
        binary_states_mr = (scores_mr > 0).astype(int)

        # Keep the majority cluster labeled as 0 for consistency
        n0_mr = np.sum(binary_states_mr == 0)
        n1_mr = np.sum(binary_states_mr == 1)
        if n1_mr > n0_mr:
            binary_states_mr = 1 - binary_states_mr
            c0_mr, c1_mr = c1_mr, c0_mr
            normal_mr = c1_mr - c0_mr
            midpoint_mr = 0.5 * (c0_mr + c1_mr)
            scores_mr = (iq_mr - midpoint_mr) @ normal_mr

        # Approximate shot timing
        tau_us_mr = float(dMR["data"]["tau_us"])
        pulse_len_us_mr = 4.0 * config_mr["sigma"]
        shot_spacing_us_mr = (
            pulse_len_us_mr
            + tau_us_mr
            + pulse_len_us_mr
            + 0.05
            + config_mr["readout_length"]
        )

        shot_idx_mr = np.arange(len(binary_states_mr))
        time_us_mr = shot_idx_mr * shot_spacing_us_mr
        time_ms_mr = time_us_mr / 1000.0
        wall_clock_mr = np.array([
            start_dt_mr + timedelta(microseconds=float(t_us))
            for t_us in time_us_mr
        ])

        dMR["data"]["binary_states"] = binary_states_mr
        dMR["data"]["time_us"] = time_us_mr
        dMR["data"]["time_ms"] = time_ms_mr
        dMR["data"]["wall_clock"] = wall_clock_mr
        dMR["data"]["kmeans_centers"] = np.array([c0_mr, c1_mr])
        dMR["data"]["shot_spacing_us"] = shot_spacing_us_mr

        timestamp_mr = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        base_mr = os.path.join(save_dir_mr, f"Cycle_{cycle_idx_mr:03d}_MR_{timestamp_mr}")

        # IQ plot with decision boundary
        I_min, I_max = shots_i_mr.min(), shots_i_mr.max()
        Q_min, Q_max = shots_q_mr.min(), shots_q_mr.max()
        I_pad = 0.05 * (I_max - I_min if I_max > I_min else 1.0)
        Q_pad = 0.05 * (Q_max - Q_min if Q_max > Q_min else 1.0)
        I_line = np.linspace(I_min - I_pad, I_max + I_pad, 400)

        vertical_line_mr = np.abs(normal_mr[1]) < 1e-12
        if not vertical_line_mr:
            Q_line = midpoint_mr[1] - (normal_mr[0] / normal_mr[1]) * (I_line - midpoint_mr[0])

        plt.figure(figsize=(6, 6))
        plt.plot(shots_i_mr, shots_q_mr, ".", alpha=0.30, label="IQ shots")
        plt.plot(c0_mr[0], c0_mr[1], "o", markersize=10, label="state 0 center")
        plt.plot(c1_mr[0], c1_mr[1], "o", markersize=10, label="state 1 center")
        if vertical_line_mr:
            plt.axvline(midpoint_mr[0], linestyle="--", label="decision boundary")
        else:
            plt.plot(I_line, Q_line, "--", label="decision boundary")
        plt.xlabel("I (a.u.)")
        plt.ylabel("Q (a.u.)")
        plt.axis("equal")
        plt.title(
            f"Modified Ramsey IQ\n"
            f"cycle={cycle_idx_mr}, df={chosen_peak_sep_mr:.6f} MHz, tau={tau_us_mr:.6f} us"
        )
        plt.legend()
        plt.tight_layout()
        plt.savefig(base_mr + "_IQClassified.png", dpi=200)
        plt.close()

        # 0/1 vs shot number
        plt.figure(figsize=(12, 3))
        plt.step(shot_idx_mr, binary_states_mr, where="mid")
        plt.ylim(-0.2, 1.2)
        plt.xlabel("Shot index")
        plt.ylabel("State")
        plt.title(
            f"Modified Ramsey states vs shot\n"
            f"cycle={cycle_idx_mr}, df={chosen_peak_sep_mr:.6f} MHz, tau={tau_us_mr:.6f} us"
        )
        plt.tight_layout()
        plt.savefig(base_mr + "_States_vs_Shot.png", dpi=200)
        plt.close()

        # 0/1 vs relative time in ms
        plt.figure(figsize=(12, 3))
        plt.step(time_ms_mr, binary_states_mr, where="mid")
        plt.ylim(-0.2, 1.2)
        plt.xlabel("Time (ms)")
        plt.ylabel("State")
        plt.title(
            f"Modified Ramsey states vs time\n"
            f"cycle={cycle_idx_mr}, df={chosen_peak_sep_mr:.6f} MHz, tau={tau_us_mr:.6f} us"
        )
        plt.tight_layout()
        plt.savefig(base_mr + "_States_vs_Time_ms.png", dpi=200)
        plt.close()

        # 0/1 vs wall clock time
        plt.figure(figsize=(12, 3))
        plt.step(wall_clock_mr, binary_states_mr, where="mid")
        plt.ylim(-0.2, 1.2)
        plt.xlabel("Wall clock time")
        plt.ylabel("State")
        plt.title(
            f"Modified Ramsey states vs wall clock\n"
            f"cycle={cycle_idx_mr}, df={chosen_peak_sep_mr:.6f} MHz, tau={tau_us_mr:.6f} us"
        )
        ax = plt.gca()
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M:%S"))
        plt.xticks(rotation=20)
        plt.tight_layout()
        plt.savefig(base_mr + "_States_vs_WallClock.png", dpi=200)
        plt.close()

        # Moving average to make parity switching easier to see
        window_mr = min(200, max(10, len(binary_states_mr) // 20))
        kernel_mr = np.ones(window_mr) / window_mr
        smooth_states_mr = np.convolve(binary_states_mr, kernel_mr, mode="same")

        plt.figure(figsize=(12, 3))
        plt.plot(time_ms_mr, smooth_states_mr)
        plt.ylim(-0.05, 1.05)
        plt.xlabel("Time (ms)")
        plt.ylabel(f"Mean state ({window_mr} shots)")
        plt.title(
            f"Modified Ramsey moving-average state\n"
            f"cycle={cycle_idx_mr}, df={chosen_peak_sep_mr:.6f} MHz, tau={tau_us_mr:.6f} us"
        )
        plt.tight_layout()
        plt.savefig(base_mr + "_States_MovingAverage_ms.png", dpi=200)
        plt.close()

        # Save raw classified outputs too
        np.savez(
            base_mr + ".npz",
            shots_i=shots_i_mr,
            shots_q=shots_q_mr,
            binary_states=binary_states_mr,
            time_us=time_us_mr,
            time_ms=time_ms_mr,
            wall_clock_str=np.array([dt.strftime("%Y-%m-%d %H:%M:%S.%f") for dt in wall_clock_mr]),
            shot_spacing_us=np.array(shot_spacing_us_mr),
            peak_freqs=np.array(chosen_peak_freqs_mr),
            chosen_probe_freq=np.array(chosen_probe_freq_mr),
            peak_sep=np.array(chosen_peak_sep_mr),
            tau_us=np.array(tau_us_mr),
            cycle_idx=np.array(cycle_idx_mr),
            kmeans_centers=np.array([c0_mr, c1_mr]),
            config=np.array(config_mr, dtype=object),
        )

        cycle_summary_mr.append({
            "cycle_idx": cycle_idx_mr,
            "success": True,
            "chosen_probe_freq": chosen_probe_freq_mr,
            "peak_sep": chosen_peak_sep_mr,
            "tau_us": tau_us_mr,
            "png_base": base_mr,
        })

        # after finishing this cycle, restart the search automatically

    summary_path_mr = os.path.join(
        save_dir_mr,
        f"CycleSummary_{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.json"
    )
    with open(summary_path_mr, "w") as f:
        json.dump(cycle_summary_mr, f, indent=2, default=float)