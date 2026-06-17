import os
# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../.."))


import numpy as np
import matplotlib.pyplot as plt

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleTone import SingleTone
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleTone_qubit import SingleTone_qubit

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

# new for AC Stark
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mACStarkCalibration import ACStarkCalibration
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mACStarkCalibration_2 import ACStarkCalibration_2
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1ACStark import T1ACStark


# from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
# from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift
# from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF import SingleShotProgramFF
# from q4diamond.Client_modules.Experiment_Scripts.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF


soc, soccfg = makeProxy()

# # Device 2
# Qubit_Parameters = {
#     "1": {"Readout": {"Frequency": 6628.785, "Gain": 3500},
#           "Qubit": {"Frequency": 1340.82376, "Gain": 9000, "sigma": 2.2, "flattop_length": None},
#           "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 2 KOH + SiOx JJ (2 CLs)/RFSOC/Q1_6p63//"},
#
#     "2": {"Readout": {"Frequency": 6720, "Gain": 3000},
#           "Qubit": {"Frequency": 1434.62189, "Gain": 6020, "sigma": 2.2, "flattop_length": None},
#           "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 2 KOH + SiOx JJ (2 CLs)/RFSOC/Q2_6p72//"},
#
#     "3": {"Readout": {"Frequency": 6818.7, "Gain": 2500},
#           "Qubit": {"Frequency": 1663, "Gain": 15000, "sigma": 2.2, "flattop_length": None},
#           "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 2 KOH + SiOx JJ (2 CLs)/RFSOC/Q3_6p82//"},
#
#     "4": {"Readout": {"Frequency": 6913.22, "Gain": 4400},
#           "Qubit": {"Frequency":  2047.375, "Gain": 1089, "sigma": 0.5, "flattop_length": None},
#           "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 2 KOH + SiOx JJ (2 CLs)/RFSOC/Q4_6p91//"},
# }

# Device 4 KOH Stats
Qubit_Parameters = {
    "1": {"Readout": {"Frequency": 6649.4, "Gain": 7500},
          "Qubit": {"Frequency": 1723.4209400990, "Gain": 15000, "sigma": 2.2, "flattop_length": None},
          "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q1/"},

    "2": {"Readout": {"Frequency": 6767, "Gain": 10000},
          "Qubit": {"Frequency": 1862.65, "Gain": 18000, "sigma": 2.2, "flattop_length": None},  # 0.03 sigma
          "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q2/"},

    "3": {"Readout": {"Frequency": 6853.4, "Gain": 9000},
          "Qubit": {"Frequency": 2106.9739, "Gain": 4200, "sigma": 1.5, "flattop_length": None},
          "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q3/"},

    "4": {"Readout": {"Frequency": 6946.126, "Gain": 6000},
          "Qubit": {"Frequency": 2248.97, "Gain": 1218, "sigma": 1, "flattop_length": None},
          "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q4/"},
}

# Readout
Qubit_Readout = 1
Qubit_Pulse = 1
outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

ConstantTone = False  # determine cavity frequency
ConstantTone_qubit = False  # For testing the qubit amplification & filtering

RunTransmissionSweep = False   # determine cavity frequency
Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain": 5000, "SpecSpan": 10, "SpecNumPoints": 101,
                        "reps": 10, 'rounds': 10,
                        'Gauss': False, "sigma": 1.2, "gain": 5000}  # False -- no pulse #If you don't see RabiAmp but with Gauss True see the qubit, the next thing to check is gain, you might not have the right pi pulse
                        # The last 3 params are for the qubit tone. Default readout length is 30 us.
                        # Gauss: True => 4 sigma Gaussian pulse with "sigma" and "gain" from Spec_relevant_params
                        # Gauss: False => Constant tone with default pulse length = 100 us and "qubit_gain" from Spec_relevant_params
RunChiShift = False
ChiShift_params = {"reps": 1000,
                    'rounds': 1,# this will used for all experiements below unless otherwise changed in between trials
                    "TransSpan": 0.8,  ### MHz, span will be center+/- this parameter
                    "TransNumPoints": 81,
                    "cavity_shift": 0.2,
                    "relax_delay": 4000}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "min_gain": 0, "max_gain": 30000, 'number_of_steps': 201,
                         "reps": 15, 'rounds': 15,
                         'relax_delay': 11000}  #Always change the max gain if you don't see it, also compare what you get with Transmission data

RunT1 = False
RunT2 = False
T1T2_params = {"T1_step": 110, "T1_expts": 100, "T1_reps": 10, "T1_rounds": 10,
               "T2_step": 5, "T2_expts": 100, "T2_reps": 10, "T2_rounds": 10, "freq_shift": 0.02,
               "relax_delay": 11000,
               'repetitions': 1}

RunT2E = False
T2E_params = {"T2_max_us": 200, "T2_expts": 100, "T2_reps": 20, "T2_rounds": 20, "freq_shift": 0.01,
               "relax_delay": 3000, 'num_pi_pulses': 1, #need odd number of pulses
               "pi2_gain": 5000,
              "rotation_angle": None,
              "min_max": None
              # "rotation_angle": 0.31478884,
              # "min_max": [7.066475706582131, 0.4586852251182118]}
              }

RunACStarkCalibration = False
ACStark_params = {"T1_step": 5, "T1_expts": 100, "T1_reps": 10, "T1_rounds": 10,
               "T2_step": 2, "T2_expts": 2, "T2_reps": 100, "T2_rounds": 40, "freq_shift": 0.1,
               "relax_delay": 500,
               'repetitions': 10000,

               # additional AC Stark arguments
               "ACStark_detuning": 50, # PLACEHOLDER
               "ACStark_amplitude": 2000 # PLACEHOLDER
               }
RunACStarkCalibration_loop = False

RunACStarkCalibration_2 = False
ACStark_2_params = {"T1_step": 5, "T1_expts": 100, "T1_reps": 10, "T1_rounds": 10,
                  "T2_step": 0.1, "T2_expts": 201, "T2_reps": 50, "T2_rounds": 40, "freq_shift": 0.1,
                  "relax_delay": 500,
                  'repetitions': 1,

                  # additional AC Stark arguments
                  "ACStark_detuning": 50,  # PLACEHOLDER
                  "ACStark_amplitude_start": 0,  # PLACEHOLDER
                  "ACStark_amplitude_step": 550,  # PLACEHOLDER
                  "ACStark_amplitude_expts": 11,  # PLACEHOLDER
                  }

RunT1ACStark = False
RunT1ACStark_withSS = False
B = 89.1187
A = 2.8043e-5
f_max = A*5500**2+B
f_list = B + np.arange(0, 56)*(f_max-B)/55
acstark_amp_list = np.sqrt((f_list-B)/A)
T1ACStark_params = {"T1_start": 50, "T1_step": 1, "T1_expts": 1, "T1_reps": 25, "T1_rounds": 25,
                  "T2_step": 1, "T2_expts": 1, "T2_reps": 100, "T2_rounds": 20, "freq_shift": 0.1,
                  "relax_delay": 500,
                  'repetitions': 100,

                  # additional AC Stark arguments
                  "ACStark_detuning": 50,  # PLACEHOLDER
                  "ACStark_amplitude_start": 0,  # PLACEHOLDER
                  "ACStark_amplitude_step": 500,  # PLACEHOLDER
                  "ACStark_amplitude_expts": 11,  # PLACEHOLDER
                  "ACStark_amplitude_list": acstark_amp_list, # customized amplitude list
                  'reps_per_SS_cal': 3,
                  }

SingleShot = False
SS_params = {"Shots": 500, "Readout_Time": 25, "ADC_Offset": 0.5, "Qubit_Pulse": [Qubit_Pulse],
             'number_of_pulses': 1, 'relax_delay': 11000}

RunT1SS = False
T1SS_params = {"T1_step": 75, "T1_expts": 40,
               "reps": 1000,
               'angle': 0.38920197938248996, 'threshold': 1.6117224595654793,
               "relax_delay": 5000,
               'calibrate_SS': True,
               'repetitions': 120}

SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 5000, "gain_stop": 9000, "gain_pts": 7, "span": 0.2, "trans_pts": 5}

SingleShot_QubitOptimize = True
#gain_span is now in percent
SS_Q_params = {"q_gain_span": 1.4, "q_gain_pts": 28, "q_freq_span": 0.1, "q_freq_pts": 5,
               'number_of_pulses': 1} # for optimizing pi/2 pulse, set the gain to the half of its value and optimize for n=2

cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']

qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']


trans_config = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 15,  # [us]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 0.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 101,  ### number of points in the transmission frequecny
    "cav_relax_delay": 30
}
qubit_config = {
    "qubit_pulse_style": "const",
    "qubit_gain": Spec_relevant_params["qubit_gain"],
    "qubit_freq": qubit_frequency_center,
    "qubit_length": 100,
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

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

if ConstantTone:
    Instance_trans = SingleTone(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = SingleTone.acquire(Instance_trans)
if ConstantTone_qubit:
    Instance_trans = SingleTone_qubit(path="TransmissionFF_qubit", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = SingleTone_qubit.acquire(Instance_trans)

cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak
# perform the cavity transmission experiment
if RunTransmissionSweep:
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
else:
    print("Cavity frequency set to: ", config["pulse_freq"])



# qubit spec experiment
if Run2ToneSpec:
    config["reps"] = Spec_relevant_params['reps']  # want more reps and rounds for qubit data
    config["rounds"] = Spec_relevant_params['rounds']
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
    Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
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
    step = int((Amplitude_Rabi_params["max_gain"]-Amplitude_Rabi_params["min_gain"])/ number_of_steps)
    ARabi_config = {'start': Amplitude_Rabi_params["min_gain"], 'step': step, "expts": number_of_steps, "reps": Amplitude_Rabi_params['reps'],
                    "rounds": Amplitude_Rabi_params['rounds'],
                    "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": Amplitude_Rabi_params["relax_delay"],
                    "flattop_length": qubit_flattop}

    config = config | ARabi_config
    if qubit_flattop != None:
        ARabi_config = {'gain_start': 0, "gain_end": Amplitude_Rabi_params["max_gain"],
                        'gainNumPoints': number_of_steps,
                        "reps": Amplitude_Rabi_params['reps'],
                        "rounds": Amplitude_Rabi_params['rounds'],
                        "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
                        "relax_delay": 5000,
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


if RunT2:
    for i in range(T1T2_params['repetitions']):
        if T1T2_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True
        T2R_cfg = {"start": 0, "step": T1T2_params["T2_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
                   "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
                   "pi_gain": qubit_gain,
                   "pi2_gain": qubit_gain // 2, "relax_delay": T1T2_params["relax_delay"],
                   'f_ge': qubit_frequency_center + T1T2_params["freq_shift"],
                   "sigma": qubit_sigma, "flattop_length": qubit_flattop
                   }
        config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT2R = T2R.acquire(iT2R)
        T2R.display(iT2R, dT2R, plotDisp=plot_disp, figNum=2)
        T2R.save_data(iT2R, dT2R)
        T2R.save_config(iT2R)

# AC Stark calibration
if RunACStarkCalibration:
    for i in range(ACStark_params['repetitions']):
        if ACStark_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True
        ACStarkCalibration_cfg = {"start": 0.01, "step": ACStark_params["T2_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=config["qubit_ch"]),
                   "expts": ACStark_params["T2_expts"], "reps": ACStark_params["T2_reps"], "rounds": ACStark_params["T2_rounds"],
                   "pi_gain": qubit_gain,
                   "pi2_gain": qubit_gain // 2, "relax_delay": ACStark_params["relax_delay"],
                   'f_ge': qubit_frequency_center + ACStark_params["freq_shift"],
                   "sigma": qubit_sigma, "flattop_length": qubit_flattop,

                    # AC Stark
                    "ACStark_detuning": ACStark_params["ACStark_detuning"],
                    "ACStark_amplitude": ACStark_params["ACStark_amplitude"]
                   }
        config = config | ACStarkCalibration_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iACStarkCalibration = ACStarkCalibration(path="ACStarkCalibration", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dACStarkCalibration = ACStarkCalibration.acquire(iACStarkCalibration)
        ACStarkCalibration.display(iACStarkCalibration, dACStarkCalibration, plotDisp=plot_disp, figNum=2)
        ACStarkCalibration.save_data(iACStarkCalibration, dACStarkCalibration)
        ACStarkCalibration.save_config(iACStarkCalibration)

acstark_calibration_data = []
if RunACStarkCalibration_loop:
    acstark_amp_list = np.linspace(0,1500,61)
    for amp in acstark_amp_list:
        ACStarkCalibration_cfg = {"start": 0.01, "step": ACStark_params["T2_step"],
                                  "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=config["qubit_ch"]),
                                  "expts": ACStark_params["T2_expts"], "reps": ACStark_params["T2_reps"],
                                  "rounds": ACStark_params["T2_rounds"],
                                  "pi_gain": qubit_gain,
                                  "pi2_gain": qubit_gain // 2, "relax_delay": ACStark_params["relax_delay"],
                                  'f_ge': qubit_frequency_center + ACStark_params["freq_shift"],
                                  "sigma": qubit_sigma, "flattop_length": qubit_flattop,

                                  # AC Stark
                                  "ACStark_detuning": ACStark_params["ACStark_detuning"],
                                  "ACStark_amplitude": int(amp)
                                  }
        config = config | ACStarkCalibration_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iACStarkCalibration = ACStarkCalibration(path="ACStarkCalibration", cfg=config, soc=soc, soccfg=soccfg,
                                                 outerFolder=outerFolder)
        dACStarkCalibration = ACStarkCalibration.acquire(iACStarkCalibration)
        acstark_calibration_data.append(ACStarkCalibration.display(iACStarkCalibration, dACStarkCalibration, plotDisp=False, figNum=2))
        ACStarkCalibration.save_data(iACStarkCalibration, dACStarkCalibration)
        ACStarkCalibration.save_config(iACStarkCalibration)

    import os
    import json
    import datetime

    data_array = np.array(acstark_calibration_data)
    Rfreq_list = data_array[:, 2]
    save_dir = os.path.dirname(iACStarkCalibration.iname)
    timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    # quadratic fit
    Rfreq_list_kHz = Rfreq_list * 1e3
    coeffs = np.polyfit(acstark_amp_list, Rfreq_list_kHz, 2)
    a, b, c = coeffs
    x_fit = np.linspace(acstark_amp_list[0], acstark_amp_list[-1], 300)
    y_fit = np.polyval(coeffs, x_fit)
    date_str = datetime.datetime.now().strftime("%Y_%m_%d")
    title_str = f"ACStarkCalibration_{date_str}_{a:.4f}x^2+{b:.4f}x+{c:.4f}"
    with open(os.path.join(save_dir, f'ACStarkCalibration_amp_sweep_{timestamp}.json'), 'w') as f:
        json.dump({'acstark_amp_list': acstark_amp_list.tolist(), 'data_array': data_array.tolist()}, f)

    plt.figure()
    plt.plot(acstark_amp_list, Rfreq_list*1e3, 'o', label="data", color='orange')
    plt.plot(x_fit, y_fit, '-', label=f"fit", color='black')
    plt.xlabel("AC Stark Amplitude (a.u.)")
    plt.ylabel("Ramsey Frequency (kHz)")
    plt.title(title_str)
    plt.legend()
    plt.savefig(os.path.join(save_dir, f'ACStarkCalibration_amp_sweep_{timestamp}.png'))
    plt.show()



if RunACStarkCalibration_2:
    ACStarkCalibration_2_cfg = {"start": 0.01, "step": ACStark_2_params["T2_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=config["qubit_ch"]),
               "expts": ACStark_2_params["T2_expts"], "reps": ACStark_2_params["T2_reps"], "rounds": ACStark_2_params["T2_rounds"],
               "pi_gain": qubit_gain,
               "pi2_gain": qubit_gain // 2, "relax_delay": ACStark_2_params["relax_delay"],
               'f_ge': qubit_frequency_center + ACStark_2_params["freq_shift"],
               "sigma": qubit_sigma, "flattop_length": qubit_flattop,

                # AC Stark
                "ACStark_detuning": ACStark_2_params["ACStark_detuning"],
                # IMPORTANT: RFSOC only accepts integer amplitudes
                "ACStark_amplitude_start": ACStark_2_params["ACStark_amplitude_start"],
                "ACStark_amplitude_step": ACStark_2_params["ACStark_amplitude_step"],
                "ACStark_amplitude_expts": ACStark_2_params["ACStark_amplitude_expts"],
               }
    config = config | ACStarkCalibration_2_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iACStarkCalibration_2 = ACStarkCalibration_2(path="ACStarkCalibration_2", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dACStarkCalibration_2 = ACStarkCalibration_2.acquire(iACStarkCalibration_2)
    ACStarkCalibration_2.display(iACStarkCalibration_2, dACStarkCalibration_2, plotDisp=True, figNum=2)
    ACStarkCalibration_2.save_data(iACStarkCalibration_2, dACStarkCalibration_2)
    ACStarkCalibration_2.save_config(iACStarkCalibration_2)

if RunT1ACStark:
    for i in range(T1ACStark_params['repetitions']):
        T1ACStark_cfg = {"start": T1ACStark_params["T1_start"], "step": T1ACStark_params["T1_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=config["qubit_ch"]),
                   "expts": T1ACStark_params["T1_expts"], "reps": T1ACStark_params["T1_reps"], "rounds": T1ACStark_params["T1_rounds"],
                   "pi_gain": qubit_gain,
                   "pi2_gain": qubit_gain // 2, "relax_delay": T1ACStark_params["relax_delay"],
                   'f_ge': qubit_frequency_center, # + T1ACStark_params["freq_shift"],
                   "sigma": qubit_sigma, "flattop_length": qubit_flattop,

                    # AC Stark
                    "ACStark_detuning": T1ACStark_params["ACStark_detuning"],
                    # IMPORTANT: RFSOC only accepts integer amplitudes
                    "ACStark_amplitude_start": T1ACStark_params["ACStark_amplitude_start"],
                    "ACStark_amplitude_step": T1ACStark_params["ACStark_amplitude_step"],
                    "ACStark_amplitude_expts": T1ACStark_params["ACStark_amplitude_expts"],
                    "ACStark_amplitude_list": T1ACStark_params["ACStark_amplitude_list"],
                   }
        config = config | T1ACStark_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT1ACStark = T1ACStark(path="T1ACStark", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)

        if T1ACStark_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True
        dT1ACStark = T1ACStark.acquire(iT1ACStark)
        T1ACStark.display(iT1ACStark, dT1ACStark, plotDisp=plot_disp, figNum=2)
        T1ACStark.save_data(iT1ACStark, dT1ACStark)
        T1ACStark.save_config(iT1ACStark)

'''if RunT1ACStark_withSS:
    for i in range(T1ACStark_params['repetitions']):
        # first do SS and remember rotation angle
        config['shots'] = 1000
        config['number_of_pulses'] = SS_params['number_of_pulses']
        Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                            soc=soc, soccfg=soccfg)
        data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
        # print(data_SingleShotProgram)
        SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

        SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
        SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
        print('Angle: ', data_SingleShotProgram['data']['angle'][0])
        print('threshold: ', data_SingleShotProgram['data']['threshold'][0])

        angle = data_SingleShotProgram['data']['angle'][0]

        for j in range(T1ACStark_params['reps_per_SS_cal']):
            T1ACStark_cfg = {"start": T1ACStark_params["T1_start"], "step": T1ACStark_params["T1_step"],
                             "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=config["qubit_ch"]),
                             "expts": T1ACStark_params["T1_expts"], "reps": T1ACStark_params["T1_reps"],
                             "rounds": T1ACStark_params["T1_rounds"],
                             "pi_gain": qubit_gain,
                             "pi2_gain": qubit_gain // 2, "relax_delay": T1ACStark_params["relax_delay"],
                             'f_ge': qubit_frequency_center,  # + T1ACStark_params["freq_shift"],
                             "sigma": qubit_sigma, "flattop_length": qubit_flattop,

                             # AC Stark
                             "ACStark_detuning": T1ACStark_params["ACStark_detuning"],
                             # IMPORTANT: RFSOC only accepts integer amplitudes
                             "ACStark_amplitude_start": T1ACStark_params["ACStark_amplitude_start"],
                             "ACStark_amplitude_step": T1ACStark_params["ACStark_amplitude_step"],
                             "ACStark_amplitude_expts": T1ACStark_params["ACStark_amplitude_expts"],
                             "ACStark_amplitude_list": T1ACStark_params["ACStark_amplitude_list"],
                             "rotation_angle": angle
                             }
            config = config | T1ACStark_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
            iT1ACStark = T1ACStark(path="T1ACStark", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)

            if T1ACStark_params['repetitions'] > 1:
                plot_disp = False
            else:
                plot_disp = True
            dT1ACStark = T1ACStark.acquire(iT1ACStark)
            T1ACStark.display(iT1ACStark, dT1ACStark, plotDisp=plot_disp, figNum=2)
            T1ACStark.save_data(iT1ACStark, dT1ACStark)
            T1ACStark.save_config(iT1ACStark)'''



if RunT2E:
    if T2E_params["pi2_gain"] == False:
        qubit_gain_pi2 = qubit_gain // 2
    else:
        qubit_gain_pi2 = T2E_params["pi2_gain"]
    num_pulses = T2E_params["num_pi_pulses"]
    int_steps = T2E_params["T2_max_us"] // (0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"])
    print(int_steps, 0.00232515 * (num_pulses + 1) * int_steps, T2E_params["T2_expts"])
    T2E_cfg = {"start": 0, "step": 0.00232515 * (num_pulses + 1) * int_steps,
               "expts": T2E_params["T2_expts"], "reps": T2E_params["T2_reps"], "rounds": T2E_params["T2_rounds"],
               "pi_gain": qubit_gain,
               "pi2_gain": qubit_gain_pi2, "relax_delay": T2E_params["relax_delay"],
               'f_ge': qubit_frequency_center + T2E_params["freq_shift"],
               "num_pi_pulses": T2E_params["num_pi_pulses"],
               "sigma": qubit_sigma, "flattop_length": qubit_flattop
               }
    if T2E_params["rotation_angle"] != False:
        T2E_cfg["rotation_angle"] = T2E_params["rotation_angle"]
        T2E_cfg["min_max"] = T2E_params["min_max"]

    if int_steps == 0:
        print('Step size is 0! need to increase total time or decrease experiments')
    else:
        config = config | T2E_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT2E = T2EMUX(path="T2E", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT2E = T2EMUX.acquire(iT2E)
        T2EMUX.display(iT2E, dT2E, plotDisp=True, figNum=2)
        T2EMUX.save_data(iT2E, dT2E)
        T2EMUX.save_config(iT2E)




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

# Moved this below UpdateConfig
if RunT1ACStark_withSS:
    for i in range(T1ACStark_params['repetitions']):
        # first do SS and remember rotation angle
        # config['shots'] = 1000
        config['number_of_pulses'] = SS_params['number_of_pulses']
        Instance_SingleShotProgram = SingleShotProgramFFMUX(path="T1ACStark_SS", outerFolder=outerFolder, cfg=config,
                                                            soc=soc, soccfg=soccfg)
        data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
        # print(data_SingleShotProgram)
        SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)

        SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
        SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
        print('Angle: ', data_SingleShotProgram['data']['angle'][0])
        print('threshold: ', data_SingleShotProgram['data']['threshold'][0])

        angle = data_SingleShotProgram['data']['angle'][0]

        for j in range(T1ACStark_params['reps_per_SS_cal']):
            T1ACStark_cfg = {"start": T1ACStark_params["T1_start"], "step": T1ACStark_params["T1_step"],
                             "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=config["qubit_ch"]),
                             "expts": T1ACStark_params["T1_expts"], "reps": T1ACStark_params["T1_reps"],
                             "rounds": T1ACStark_params["T1_rounds"],
                             "pi_gain": qubit_gain,
                             "pi2_gain": qubit_gain // 2, "relax_delay": T1ACStark_params["relax_delay"],
                             'f_ge': qubit_frequency_center,  # + T1ACStark_params["freq_shift"],
                             "sigma": qubit_sigma, "flattop_length": qubit_flattop,

                             # AC Stark
                             "ACStark_detuning": T1ACStark_params["ACStark_detuning"],
                             # IMPORTANT: RFSOC only accepts integer amplitudes
                             "ACStark_amplitude_start": T1ACStark_params["ACStark_amplitude_start"],
                             "ACStark_amplitude_step": T1ACStark_params["ACStark_amplitude_step"],
                             "ACStark_amplitude_expts": T1ACStark_params["ACStark_amplitude_expts"],
                             "ACStark_amplitude_list": T1ACStark_params["ACStark_amplitude_list"],
                             "rotation_angle": angle
                             }
            config = config | T1ACStark_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
            iT1ACStark = T1ACStark(path="T1ACStark_SS", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
            dT1ACStark = T1ACStark.acquire(iT1ACStark)
            T1ACStark.display(iT1ACStark, dT1ACStark, plotDisp=False, figNum=2)
            T1ACStark.save_data(iT1ACStark, dT1ACStark)
            T1ACStark.save_config(iT1ACStark)





if SingleShot:
    config['number_of_pulses'] = SS_params['number_of_pulses']
    # print(config)
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
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
        "qubit_gain_Start": max([0, int(qubit_gains[Qubit_Pulse_Index] * (1 - q_gain_span))]), # - q_gain_span / 2,
        "qubit_gain_Stop":  min([32767, int(qubit_gains[Qubit_Pulse_Index] * (1 + q_gain_span))]),# *qubit_gains[Qubit_Pulse_Index] + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_centers[Qubit_Pulse_Index] - q_freq_span / 2, #249.6,
        "qubit_freq_stop": qubit_frequency_centers[Qubit_Pulse_Index] + q_freq_span / 2, #250.3,
        "QubitNumPoints": q_freq_pts,
        "number_of_pulses": SS_Q_params["number_of_pulses"]
    }
    config = config | exp_parameters
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