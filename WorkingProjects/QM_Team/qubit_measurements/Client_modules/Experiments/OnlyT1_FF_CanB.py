# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF import AmplitudeRabiFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF_NoUpdate import T1FF_N


soc, soccfg = makeProxy()

#### define the saving path

#Readout Qubit Params
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6675.5, 'Gain': int(4000)},
#           'Qubit': {'Frequency': 3010.3, 'Gain': int(9000), "sigma": 0.1, "flattop_length": 1.0},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATP01-Si_01/Q1_Q6//"},
#     '2': {'Readout': {'Frequency': 6818.2, 'Gain': 2900},
#           'Qubit': {'Frequency': 3315.9, 'Gain': 6200, "sigma": 0.01, "flattop_length": 0.07}, #0.03 sigma
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATP01-Si_01/Q2_6p82//"},
#     '3': {'Readout': {'Frequency': 6898.6, 'Gain': 3500 },
#           'Qubit': {'Frequency': 3390.8, 'Gain': 7400, "sigma": 0.1, "flattop_length": 0.7},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATP01-Si_01/Q3_6p899//"},
#     '4': {'Readout': {'Frequency': 6966.7, 'Gain': 3000},
#           'Qubit': {'Frequency': 3701, 'Gain': 3100, "sigma": 0.1, "flattop_length": 1.0},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATP01-Si_01/Q4_6p967//"},
#     '5': {'Readout': {'Frequency': 7101.65, 'Gain': 2500},
#           'Qubit': {'Frequency': 3708.98, 'Gain': 6000, "sigma": 0.1, "flattop_length": 20.0},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATP01-Si_01/Q5_7p107//"},
#     '6': {'Readout': {'Frequency': 7142.58, 'Gain': 3800},
#           'Qubit': {'Frequency': 4020, 'Gain': 7300, "sigma": 0.03, "flattop_length": 0.3},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATP01-Si_01/Q1_Q6//"},
#     }

############### Start Can B ############################
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6514, 'Gain': int(4000)},
          'Qubit': {'Frequency': 2980, 'Gain': int(9000), "sigma": 0.1, "flattop_length": 1.0},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q1_6p5//"},
    '2': {'Readout': {'Frequency': 6631, 'Gain': 2300},
          'Qubit': {'Frequency': 3197.64, 'Gain': 9000, "sigma": 0.3, "flattop_length": 2.5}, #0.03 sigma
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q2_6p6//"},
    '3': {'Readout': {'Frequency': 6766.2, 'Gain': 3500 },
          'Qubit': {'Frequency': 3525, 'Gain': 7400, "sigma": 0.1, "flattop_length": 0.7},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q3_6p7//"},
    '4': {'Readout': {'Frequency': 6839.8, 'Gain': 1000},
          'Qubit': {'Frequency': 3577.04, 'Gain': 6400, "sigma": 0.01, "flattop_length": 0.04},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q4_6p8//"},
    '5': {'Readout': {'Frequency': 7019.15, 'Gain': 1600},
          'Qubit': {'Frequency': 3893.44, 'Gain': 7850, "sigma": 0.03, "flattop_length": 0.3},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q5_7p0//"},
    '6': {'Readout': {'Frequency': 7077.9, 'Gain': 3000},
          'Qubit': {'Frequency': 4024.7, 'Gain': 7300, "sigma": 0.03, "flattop_length": 1.3},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q6_7p1//"},
    }
############### End Can B ############################

############## Start Can C ############################
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6715.6, 'Gain': int(4000)},
#           'Qubit': {'Frequency': 3862.9, 'Gain': int(6500), "sigma": 0.03, "flattop_length": 0.3},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATAl01-Si_01/Q1_Q3_Q6//"},
#     '3': {'Readout': {'Frequency': 6922.7, 'Gain': 4000},
#           'Qubit': {'Frequency': 4255.497, 'Gain': 8000, "sigma": 0.2, "flattop_length": 7}, #0.03 sigma
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATAl01-Si_01/Q1_Q3_Q6//"},
#     '5': {'Readout': {'Frequency': 7131.8, 'Gain': 4000},
#           'Qubit': {'Frequency': 4558.925, 'Gain': 14000, "sigma": 0.2, "flattop_length": 140},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATAl01-Si_01/Q1_Q3_Q6//"},
#     '6': {'Readout': {'Frequency': 7203.9, 'Gain': 3000},
#           'Qubit': {'Frequency': 4964.64, 'Gain': 9500, "sigma": 0.3, "flattop_length": 7},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATAl01-Si_01/Q1_Q3_Q6//"},
#     }
############## End Can C ############################
# Readout

T1_qubitsweep = True
T1T2_params = {"qubit_swept": [1, 3, 6], "T1_step": 50, "T1_expts": 100, "T1_reps": 15, "T1_rounds": 20,
               "relax_delay": 6000}

T1_switchsweep = False
T1T2_switch = {"qubit_number": 2,
               "trig_buffer_end_list": [0.03],
               "outer_loop": False}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {
                         "reps": 3000, 'rounds': 1,
                         'relax_delay': 5000,}
repetition_number = 1000


if T1_qubitsweep:
    for rep in range(repetition_number):
        for i in T1T2_params["qubit_swept"]:
            from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import BaseConfig

            Qubit_Readout = i
            Qubit_Pulse = i
            outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

            cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
            resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
            qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
            qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']
            qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
            qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']

            trans_config = {
                "reps": 10000,  # this will used for all experiements below unless otherwise changed in between trials
                "pulse_style": "const",  # --Fixed
                "readout_length": 10,  # [us]
                "pulse_gain": cavity_gain,  # [DAC units]
                "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
                "TransSpan": 1,  ### MHz, span will be center+/- this parameter
                "TransNumPoints": 61,  ### number of points in the transmission frequecny
                "cav_relax_delay": 30
            }

            config = BaseConfig | trans_config  ### note that UpdateConfig will overwrite elements in BaseConfig
            config["FF_Qubits"] = FF_Qubits

            cavity_min = True
            config["cavity_min"] = cavity_min  # look for dip, not peak

            number_of_steps = 3
            ARabi_config = {'gain_start': 0, "gain_end": qubit_gain,
                            'gainNumPoints': number_of_steps,
                            "reps": Amplitude_Rabi_params['reps'],
                            "rounds": Amplitude_Rabi_params['rounds'],
                            "sigma": qubit_sigma, "f_ge": qubit_frequency_center,
                            "relax_delay": 5000,
                            "flattop_length": qubit_flattop}
            config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
            iAmpRabi = AmplitudeRabiFF_N(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                         outerFolder=outerFolder)
            dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
            rotation_angle, min_max = AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=False, figNum=2)
            AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
            AmplitudeRabiFF_N.save_config(iAmpRabi)
            config["rotation_angle"] = rotation_angle
            config["min_max"] = min_max

            #
            expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                        "reps": T1T2_params["T1_reps"],
                        "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain,
                        "relax_delay": T1T2_params["relax_delay"],
                        "f_ge": qubit_frequency_center,
                        "Qubit_number": Qubit_Readout,
                        "sigma": qubit_sigma,
                        "flattop_length": qubit_flattop
                        }
            config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
            iT1 = T1FF(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
            dT1 = T1FF.acquire(iT1)
            T1FF.display(iT1, dT1, plotDisp=False, figNum=2)
            T1FF.save_data(iT1, dT1)
            T1FF.save_config(iT1)

            time.sleep(10)
            soc.reset_gens()

if T1_switchsweep:
    for rep in range(repetition_number):
        for switch_end in T1T2_switch["trig_buffer_end_list"]:
            from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import BaseConfig

            Qubit_Readout = T1T2_switch["qubit_number"]
            Qubit_Pulse = T1T2_switch["qubit_number"]
            outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

            cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
            resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
            qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
            qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']
            qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
            qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']

            trans_config = {
                "reps": 10000,  # this will used for all experiements below unless otherwise changed in between trials
                "pulse_style": "const",  # --Fixed
                "readout_length": 20,  # [us]
                "pulse_gain": cavity_gain,  # [DAC units]
                "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
                "TransSpan": 1,  ### MHz, span will be center+/- this parameter
                "TransNumPoints": 61,  ### number of points in the transmission frequecny
                "cav_relax_delay": 30
            }

            config = BaseConfig | trans_config  ### note that UpdateConfig will overwrite elements in BaseConfig
            config["FF_Qubits"] = FF_Qubits

            config["trig_buffer_end"] = switch_end
            #"start": 0, "step": T1T2_params["T1_step"],

            if T1T2_switch["outer_loop"]:
                expt_cfg = {"t1_start": 0, "t1_end": T1T2_params["T1_step"] * T1T2_params["T1_expts"],
                            "t1_NumPoints": T1T2_params["T1_expts"] + 1,
                            "reps": T1T2_params["T1_reps"],
                            "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain,
                            "relax_delay": T1T2_params["relax_delay"],
                            "f_ge": qubit_frequency_center,
                            "Qubit_number": Qubit_Readout,
                            "sigma": qubit_sigma,
                            "flattop_length": qubit_flattop
                            }
                config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
                iT1 = T1FF_N(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
                dT1 = T1FF_N.acquire(iT1)
                T1FF_N.display(iT1, dT1, plotDisp=False, figNum=2)
                T1FF_N.save_data(iT1, dT1)
                T1FF_N.save_config(iT1)
            else:
                expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                            "reps": T1T2_params["T1_reps"],
                            "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain,
                            "relax_delay": T1T2_params["relax_delay"],
                            "f_ge": qubit_frequency_center,
                            "Qubit_number": Qubit_Readout,
                            "sigma": qubit_sigma,
                            "flattop_length": qubit_flattop
                            }
                config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
                iT1 = T1FF(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
                dT1 = T1FF.acquire(iT1)
                T1FF.display(iT1, dT1, plotDisp=False, figNum=2)
                T1FF.save_data(iT1, dT1)
                T1FF.save_config(iT1)

            time.sleep(10)
            soc.reset_gens()

