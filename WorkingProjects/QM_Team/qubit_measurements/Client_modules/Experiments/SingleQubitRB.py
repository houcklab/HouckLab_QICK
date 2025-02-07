# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
import time
import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt
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
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgram_RB_Test import SingleShotProgramFFMUX_RB

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1_SS import T1_SS
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSQRB import SingleQRB
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Helpers.SQ_RB_Helpers import *

soc, soccfg = makeProxy_RFSOC_10()

#### define the saving path

############### TATQ01-CL-01 ############################
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6628.8, 'Gain': 1400},
          'Qubit': {'Frequency': 3273.87, 'Gain': 15000, "sigma": 0.2, "flattop_length": 5}, #0.1 0.3 pi: 6100, pi/2: 3050
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_01/RFSOC/Q1/"},
    # '2': {'Readout': {'Frequency': 6727.25, 'Gain': 700},
    #       'Qubit': {'Frequency': 3337.285, 'Gain': 6737, "sigma": 0.0372, "flattop_length": None}, #pi: 8100, pi/2: 4050
    #       'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_01/RFSOC/Q2/"},

    # '2': {'Readout': {'Frequency': 6727.25, 'Gain': 700},
    #       'Qubit': {'Frequency': 3337.285, 'Gain': 6737, "sigma": 0.0186, "flattop_length": None},
    #       # pi: 8100, pi/2: 4050
    #       'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_01/RFSOC/Q2/"},
    # '2': {'Readout': {'Frequency': 6727.25, 'Gain': 700},
          # 'Qubit': {'Frequency': 3337.29, 'Gain': 3892, "sigma": 0.010, "flattop_length": 0.1},  # pi: 8100, pi/2: 4050
          # 'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_01/RFSOC/Q2/"},
    # '2': {'Readout': {'Frequency': 6727.25, 'Gain': 700},
    #       'Qubit': {'Frequency': 3337.285,
    #                 'Gain': 5532, "sigma": 0.0372,
    #                 'Gain_pi2': 5532, "sigma_pi2": 0.0186,
    #                 "flattop_length": None},
    #       'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_01/RFSOC/Q2/"},

    '2': {'Readout': {'Frequency': 6727.25, 'Gain': 400},
          'Qubit': {'Frequency': 3337.28,
                    'Gain': 2773, "sigma": 0.0744,
                    'Gain_pi2': 2774, "sigma_pi2": 0.0372,
                    "flattop_length": None},
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_01/RFSOC/Q2/"},

    '3': {'Readout': {'Frequency': 6836.336, 'Gain': 3920},
          'Qubit': {'Frequency': 3499.0, 'Gain': 5000, "sigma": 0.1, "flattop_length": 0.5}, #pi: 8000, pi/2: 4000
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_01/RFSOC/Q3/"},
    '4': {'Readout': {'Frequency': 7371.936, 'Gain': 4400},
          'Qubit': {'Frequency': 4351.38, 'Gain': 7600, "sigma": 0.05, "flattop_length": 0.1}, #pi: 7600, pi/2: 3800
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_01/RFSOC/Q4/"},
    '5': {'Readout': {'Frequency': 7270.524, 'Gain': 4000},
          'Qubit': {'Frequency': 4685.7, 'Gain': 8000, "sigma": 0.1, "flattop_length": 0.75},  # pi: 8000, pi/2: 4000
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_01/RFSOC/Q5/"},
    '6': {'Readout': {'Frequency': 7371.936, 'Gain': 4400},
          'Qubit': {'Frequency': 4351.38, 'Gain': 7600, "sigma": 0.05, "flattop_length": 0.1},  # pi: 7600, pi/2: 3800
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_01/RFSOC/Q6/"}
    }

######### TATCR03-01 ##########
"""Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7057.5, 'Gain': 1700},
          'Qubit': {'Frequency': 5225.37, 'Gain': 6200, "sigma": 0.04, "flattop_length": 0.1}, #pi: 6200, pi/2: 3100
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATCR03_01/RFSOC/Q1/"},
    '2': {'Readout': {'Frequency': 7178.096, 'Gain': 1400},
          'Qubit': {'Frequency': 5206.38, 'Gain': 6000, "sigma": 0.01, "flattop_length": 0.1}, #pi: 6000, pi/2: 3000
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATCR03_01/RFSOC/Q2/"},
    }"""

############### TATQ01-CL-02 ############################
"""Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6621.3, 'Gain': 3300},
          'Qubit': {'Frequency': 3214.654, 'Gain': 6500, "sigma": 0.01, "flattop_length": 0.1},    #pi: 6500, pi/2: 3200
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_02/RFSOC/Q1/"},
    '2': {'Readout': {'Frequency': 6756.176, 'Gain': 1500 },
          'Qubit': {'Frequency': 3336.92, 'Gain': 8000, "sigma": 0.1, "flattop_length": 0.1},    #pi: , pi/2:
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_02/RFSOC/Q2/"},
    '3': {'Readout': {'Frequency': 6861.328, 'Gain': 2000},
          'Qubit': {'Frequency': 3422.5, 'Gain': 8000, "sigma": 0.3, "flattop_length": 3},     #pi: , pi/2:
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_02/RFSOC/Q3/"},
    '4': {'Readout': {'Frequency': 6943.316, 'Gain': 2800},
          'Qubit': {'Frequency': 3594.5, 'Gain': 8000, "sigma": 0.01, "flattop_length": 0.025},    #pi: , pi/2:
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_02/RFSOC/Q4/"},
    '5': {'Readout': {'Frequency': 7064.576, 'Gain': 3000},
          'Qubit': {'Frequency': 3476.5, 'Gain': 8000, "sigma": 0.3, "flattop_length": 3},     # pi: , pi/2:
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_02/RFSOC/Q5/"},
    '6': {'Readout': {'Frequency': 7137.9, 'Gain': 3000},
          'Qubit': {'Frequency': 3871, 'Gain': 8000, "sigma": 0.3, "flattop_length": 3},    # pi: , pi/2:
          'outerfoldername': "Z:/t1Team/Data/2025-01-27_cooldown/TATQ01_CL_02/RFSOC/Q6/"}
    }"""

#####################
# Readout
Qubit_Readout = 2
Qubit_Pulse = 2
outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

ConstantTone = False  # determine cavity frequency

RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain": 1000, "SpecSpan": 5, "SpecNumPoints": 101,
                        "reps": 20, 'rounds': 20,
                        'Gauss': False, "sigma": 2, "gain": 3000} # False -- no pulse #If you don't see RabiAmp but with Gauss True see the qubit, the next thing to check is gain, you might not have the right pi pulse

RunChiShift = False
ChiShift_params = {"reps": 1000,
                    'rounds': 1,
                    "TransSpan": 0.8,  ### MHz, span will be center+/- this parameter
                    "TransNumPoints": 81,
                    "cavity_shift": 0.2,
                    "relax_delay": 4000}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "max_gain": 30000, 'number_of_steps': 51,
                         "reps": 10, 'rounds': 10,
                         'relax_delay': 1000}  #Always change the max gain if you don't see it, also compare what you get with Transmission data
# Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
#                          "max_gain": 6737, 'number_of_steps': 4,
#                          "reps": 10, 'rounds': 10,
#                          'relax_delay': 3000}  #Always change the max gain if you don't see it, also compare what you get with Transmission data

RunT1 = False
RunT2 = False
T1T2_params = {"T1_step": 30, "T1_expts": 100, "T1_reps": 10, "T1_rounds": 10,
               "T2_step": 50, "T2_expts": 50, "T2_reps": 10, "T2_rounds": 10, "freq_shift": 0.1,
               "relax_delay": 1000,
               'repetitions': 1000}
# T1T2_params = {"T1_step": 50, "T1_expts": 30, "T1_reps": 10, "T1_rounds": 10,
#                "T2_step": 1.7, "T2_expts": 100, "T2_reps": 20, "T2_rounds": 20, "freq_shift": 0.25,
#                "relax_delay": 2000}
RunT2E = False
T2E_params = {"T2_max_us": 1500, "T2_expts": 100, "T2_reps": 20, "T2_rounds": 20, "freq_shift": 0.0,
               "relax_delay": 1000, 'num_pi_pulses': 1, #need odd number of pulses
               "pi2_gain": 3200,
              "rotation_angle": None,
              "min_max": None,
              'repetitions': 1000}

RunSingle_Q_RB = False
SingleShot_RB_single = True
Run_RB_SS_Sweep = False
SQ_RB_params = {'reps': 200,
                'gate_seq': generate_rbsequence(2),
                "SS_init_shots": 5000,
                'pulse_number_list': [1, 5, 20, 50, 100, 200, 300, 500, 700, 900, 1000, 1150],
                'number_of_iterations': 1000,
                'plot': True}

SingleShot = False
SS_params = {"Shots": 10000, "Readout_Time": 7, "ADC_Offset": 0.5, "Qubit_Pulse": [Qubit_Pulse],
             'number_of_pulses': 1, 'pi/2': False, 'relax_delay': 2500}

SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 300, "gain_stop": 2500, "gain_pts": 11, "span": 1, "trans_pts": 7}

SingleShot_QubitOptimize = False
#gain_span is now in percent
SS_Q_params = {"q_gain_span": 0.002, "q_gain_pts": 11, "q_freq_span": 0.1, "q_freq_pts": 11,
               'number_of_pulses': 401} # for optimizing pi/2 pulse, set the gain to the half of its value and optimize for n=2
SS_Q_params = {"q_gain_span": 0.009, "q_gain_pts": 11, "q_freq_span": 0.1, "q_freq_pts": 7,
               'number_of_pulses': 51}
SS_Q_params = {"q_gain_span": 0.003, "q_gain_pts": 15, "q_freq_span": 0.1, "q_freq_pts": 7,
               'number_of_pulses': 402}

RunT1SS = False
T1SS_params = {"T1_step": 50, "T1_expts": 100,
               "reps": 100,
               'angle': -1.2554343542620698, 'threshold': -3.1841847292341834,
               "relax_delay": 5000,
               'calibrate_SS': True,
               'repetitions': 11}

cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']

qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']


trans_config = {
    "reps": 10000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 15,  # [us]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 51,  ### number of points in the transmission frequecny
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
    #print(config)
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
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": Amplitude_Rabi_params['reps'],
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
    T2R_cfg = {"start": 0, "step": T1T2_params["T2_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
               "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
               "pi_gain": qubit_gain,"Qubit_number": Qubit_Readout,
               "pi2_gain": qubit_gain // 2, "relax_delay": T1T2_params["relax_delay"],
               'f_ge': qubit_frequency_center + T1T2_params["freq_shift"],
               "sigma": qubit_sigma, "flattop_length": qubit_flattop
               }
    config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2R.acquire(iT2R)
    T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2R.save_data(iT2R, dT2R)
    T2R.save_config(iT2R)


if RunT2E:
    for i in range(T1T2_params['repetitions']):
        if T2E_params["pi2_gain"] == False:
            qubit_gain_pi2 = qubit_gain // 2
        else:
            qubit_gain_pi2 = T2E_params["pi2_gain"]
        num_pulses = T2E_params["num_pi_pulses"]
        int_steps = T2E_params["T2_max_us"] // (0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"])
        print(int_steps, 0.00232515 * (num_pulses + 1) * int_steps, T2E_params["T2_expts"])
        T2E_cfg = {"start": 0, "step": 0.00232515 * (num_pulses + 1) * int_steps,
                   "expts": T2E_params["T2_expts"], "reps": T2E_params["T2_reps"], "rounds": T2E_params["T2_rounds"],
                   "pi_gain": qubit_gain,"Qubit_number": Qubit_Readout,
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
            T2EMUX.display(iT2E, dT2E, plotDisp=False, figNum=2)
            T2EMUX.save_data(iT2E, dT2E)
            T2EMUX.save_config(iT2E)

        time.sleep(10)
        soc.reset_gens()


#~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
if RunSingle_Q_RB:
    qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
    qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']


    q_freq = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']

    qubit_params = {'f_ge': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                    'sigma': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma'],
                    'sigma_pi2': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma_pi2'],
                    'gain': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain'],
                    'gain_pi2': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain_pi2'],
                    }
    # 'pi_sigma': pi_sigma, 'pi_gain': pi_gain, 'pi_2_gain': pi_2_gain,

    rb_config = {
        # 'gate_seq': generate_rbsequence(3),
        # 'gate_set': {
        #     "I": {
        #         "idata": gauss(mu=0, si=pi_sigma,
        #                        length=pi_length, maxv=32766),
        #         "qdata": 0 * gauss(mu=0, si=pi_sigma,
        #                        length=pi_length, maxv=32766),
        #         "phase": 0, "gain": 0, "style": "arb",
        #
        #     },
        #     "X": {
        #         "idata": gauss(mu=0, si=pi_sigma,
        #                        length=pi_length, maxv=32766),
        #         "qdata": 0 * gauss(mu=0, si=pi_sigma,
        #                        length=pi_length, maxv=32766),
        #         "phase": 0, "gain": pi_gain, "style": "arb",
        #     },
        #     "Y": {
        #         "idata": gauss(mu=0, si=pi_sigma,
        #                        length=pi_length, maxv=32766),
        #         "qdata": 0 * gauss(mu=0, si=pi_sigma,
        #                        length=pi_length, maxv=32766),
        #         "phase": -90, "gain": pi_gain, "style": "arb",
        #     },
        #     "Z": {
        #         "idata": gauss(mu=0, si=pi_sigma,
        #                        length=pi_length, maxv=32766),
        #         "qdata": 0 * gauss(mu=0, si=pi_sigma,
        #                        length=pi_length, maxv=32766),
        #         "phase": 0, "gain": 0, "style": "arb",
        #     },
        #     "X/2": {
        #         "idata": gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "qdata": 0 * gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "phase": 0, "gain": pi_2_gain, "style": "arb",
        #     },
        #     "-X/2": {
        #         "idata": gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "qdata": 0 * gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "phase": 180, "gain": pi_2_gain, "style": "arb",
        #     },
        #
        #     "Y/2": {
        #         "idata": gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "qdata": 0 * gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "phase": -90, "gain": pi_2_gain, "style": "arb",
        #     },
        #     "-Y/2": {
        #         "idata": gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "qdata": 0 * gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "phase": 90, "gain": pi_2_gain, "style": "arb",
        #     },
        #     "Z/2": {
        #         "idata": gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "qdata": 0 * gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "phase": 0, "gain": 0, "style": "arb",
        #     },
        #     "-Z/2": {
        #         "idata": gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "qdata": 0 * gauss(mu=0, si=pi_2_sigma,
        #                        length=pi_2_length, maxv=32766),
        #         "phase": 0, "gain": 0, "style": "arb",
        #     },
            'gate_set': {
                "I": {
                    "phase": 0, "gain": 0, "style": "arb",

                },
                "X": {
                    "phase": 0, "gain": qubit_params['gain'], "style": "arb",
                },
                "Y": {
                    "phase": -90, "gain": qubit_params['gain'], "style": "arb",
                },
                "Z": {
                    "phase": 0, "gain": 0, "style": "arb",
                },
                "X/2": {
                    "phase": 0, "gain": qubit_params['gain_pi2'], "style": "arb",
                },
                "-X/2": {
                    "phase": 180, "gain": qubit_params['gain_pi2'], "style": "arb",
                },

                "Y/2": {
                    "phase": -90, "gain": qubit_params['gain_pi2'], "style": "arb",
                },
                "-Y/2": {
                    "phase": 90, "gain": qubit_params['gain_pi2'], "style": "arb",
                },
                "Z/2": {
                    "phase": 0, "gain": 0, "style": "arb",
                },
                "-Z/2": {
                    "phase": 0, "gain": 0, "style": "arb",
                },

        }
    }

    config["reps"] = SQ_RB_params['reps']  # want more reps and rounds for qubit data
    rb_config['gate_seq'] = ['X', 'X']
    rb_config['all_gate_sequences'] = [
        ['X'],
        ['X', 'X', 'X'],
        ['X'],
        ['X', 'X', 'X', 'X'],
        ['X', 'X', 'X', 'X', 'X'],
        #
        # ['X', 'X', 'X'],
        # ['X', 'X'],
        # ['X', 'X', 'X', 'X', 'X'],
        # ['X', 'X'],
        #
        # # ['X/2', 'X/2'],
        # ['Y', 'Y'],
        # ['X', 'X', 'X', 'X'],
    ]

    config = config | rb_config | qubit_params
    """Testing if it runs"""

    isq_RB = SingleQRB(path="SQRB", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dsq_RB = SingleQRB.acquire(isq_RB)

    SingleQRB.display(isq_RB, dsq_RB, plotDisp=True, figNum=2)
    # SingleQRB.save_data(isq_RB, dsq_RB)
    # SingleQRB.save_config(isq_RB)

    # print(rb_config['gate_seq'])
    # rb_config['reps'] = 5000
    # rb = RBSequenceProgram(path="SQRB", cfg=config, soc=soc, soccfg=soccfg,
    #                                outerFolder=outerFolder)
    # results = rb.acquire(soc, load_pulses=True, progress=True, debug=False, single_shot=False)
    # print(np.mean(results[3]))



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
    if SS_params['pi/2'] == True:
        config['qubit_gain'] = qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain_pi2']
        config['sigma'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma_pi2']

    config['number_of_pulses'] = SS_params['number_of_pulses']
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
    print('Angle: ', data_SingleShotProgram['data']['angle'][0])
    print('threshold: ', data_SingleShotProgram['data']['threshold'][0])


if SingleShot_RB_single:
    config["shots"] = SQ_RB_params["reps"] ### this gets turned into "reps"

    qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
    qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']


    q_freq = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']

    qubit_params = {'f_ge': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                    'sigma': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma'],
                    'sigma_pi2': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma_pi2'],
                    'gain': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain'],
                    'gain_pi2': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain_pi2'],
                    }

    rb_config = {
            'gate_set': generate_gate_set(qubit_params['gain'], qubit_params['gain_pi2'])
    }

    config["reps"] = SQ_RB_params['reps']  # want more reps and rounds for qubit data
    config['gate_seq'] = SQ_RB_params['gate_seq']

    config = config | rb_config | qubit_params


    config['number_of_pulses'] = SS_params['number_of_pulses']
    Instance_SingleShotProgram = SingleShotProgramFFMUX_RB(path="SingleShotRB", outerFolder=outerFolder, cfg=config, soc=soc,
                                                        soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX_RB.acquire_single(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX_RB.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFFMUX_RB.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX_RB.save_config(Instance_SingleShotProgram)
    print('Angle: ', data_SingleShotProgram['data']['angle'][0])
    print('threshold: ', data_SingleShotProgram['data']['threshold'][0])

if Run_RB_SS_Sweep:
    config['number_of_pulses'] = 1
    config["shots"] = SQ_RB_params["SS_init_shots"] ### this gets turned into "reps"
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)
    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
    print('Angle: ', data_SingleShotProgram['data']['angle'][0])
    print('threshold: ', data_SingleShotProgram['data']['threshold'][0])

    config["shots"] = SQ_RB_params["reps"] ### this gets turned into "reps"
    qubit_params = {'f_ge': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                    'sigma': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma'],
                    'sigma_pi2': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma_pi2'],
                    'gain': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain'],
                    'gain_pi2': Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain_pi2'],
                    }
    rb_config = {
            'gate_set': {
                "I": {
                    "phase": 0, "gain": 0, "style": "arb",
                },
                "X": {
                    "phase": 0, "gain": qubit_params['gain'], "style": "arb",
                },
                "Y": {
                    "phase": -90, "gain": qubit_params['gain'], "style": "arb",
                },
                "Z": {
                    "phase": 0, "gain": 0, "style": "arb",
                },
                "X/2": {
                    "phase": 0, "gain": qubit_params['gain_pi2'], "style": "arb",
                },
                "-X/2": {
                    "phase": 180, "gain": qubit_params['gain_pi2'], "style": "arb",
                },

                "Y/2": {
                    "phase": -90, "gain": qubit_params['gain_pi2'], "style": "arb",
                },
                "-Y/2": {
                    "phase": 90, "gain": qubit_params['gain_pi2'], "style": "arb",
                },
                "Z/2": {
                    "phase": 0, "gain": 0, "style": "arb",
                },
                "-Z/2": {
                    "phase": 0, "gain": 0, "style": "arb",
                },

        }
    }
    config["reps"] = SQ_RB_params['reps']  # want more reps and rounds for qubit data
    config['gate_seq'] = SQ_RB_params['gate_seq']

    config = config | rb_config | qubit_params

    angle, threshold = data_SingleShotProgram['data']['angle'][0], data_SingleShotProgram['data']['threshold'][0]
    all_populations = []
    avg_populations = []
    err_populations = []
    for num_cliffords in SQ_RB_params['pulse_number_list']:
        print('Number cliffords: ', num_cliffords)
        ground_population = []
        for iter in range(SQ_RB_params['number_of_iterations']):
            config['gate_seq'] = generate_rbsequence(num_cliffords)
            Instance_SingleShotProgram = SingleShotProgramFFMUX_RB(path="SingleShotRB_Pop", outerFolder=outerFolder,
                                                                   cfg=config, soc=soc,
                                                                   soccfg=soccfg)
            data_SingleShotProgram = SingleShotProgramFFMUX_RB.acquire(Instance_SingleShotProgram, angle, threshold)
            ground_population.append(data_SingleShotProgram['data']['population'])
        all_populations.append(ground_population)
        avg_populations.append(np.mean(ground_population))
        err_populations.append(np.std(ground_population))
    data_SingleShotProgram['data']['all_populations'] = all_populations
    data_SingleShotProgram['data']['avg_populations'] = avg_populations
    data_SingleShotProgram['data']['err_populations'] = err_populations
    data_SingleShotProgram['data']['pulse_number_list'] = SQ_RB_params['pulse_number_list']
    data_SingleShotProgram['data']['Reps_iter'] = (SQ_RB_params['reps'], SQ_RB_params['number_of_iterations'])
    SingleShotProgramFFMUX_RB.save_data(Instance_SingleShotProgram, data_SingleShotProgram)

    # Define the model function: A * p^n + 0.5
    def model(n, A, p):
        return A * p ** n + 0.5
    params, covariance = curve_fit(model, SQ_RB_params['pulse_number_list'], avg_populations,
                                   maxfev=1000, p0 = [0.5, 0.999])
    A_fit, p_fit = params
    # Calculate the standard errors of the parameters (square root of diagonal elements of covariance matrix)
    A_error, p_error = np.sqrt(np.diag(covariance))

    # Print the results with error estimates
    print(f"Fitted parameters: A = {A_fit:.3f} ± {A_error:.3f}, p = {p_fit:.5f} ± {p_error:.5f}")

    if SQ_RB_params['plot']:
        plt.errorbar(SQ_RB_params['pulse_number_list'], avg_populations, err_populations)
        n_gate = np.linspace(min(SQ_RB_params['pulse_number_list']), max(SQ_RB_params['pulse_number_list']), 100)
        y_fit = model(n_gate, *params)
        plt.plot(n_gate, y_fit, color='red')
        plt.title(f"Fitted: p={p_fit:.5f} ± {p_error:.5f}")
        plt.xlabel('Number of Gates')
        plt.ylabel('Ground Population')
        plt.show()



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
    if SS_params['pi/2'] == True:
        config['qubit_gain'] = qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain_pi2']
        config['sigma'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma_pi2']

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