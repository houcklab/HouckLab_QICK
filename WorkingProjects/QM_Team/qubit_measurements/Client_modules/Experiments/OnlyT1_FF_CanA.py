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


soc, soccfg = makeProxy_RFSOC_10()

############### Start Can A ############################
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6675.37, 'Gain': 7700, 'readout_length' : 10},
          'Qubit': {'Frequency': 2528.35, 'Gain': 5000, "sigma": 0.2, "flattop_length": 1},  # not good
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-11-04_CoolDown/TATQ01-Si-newPlassys-01/Q1_6p75//"},
    '2': {'Readout': {'Frequency': 6789.35, 'Gain': 2000, 'readout_length' : 10},
          'Qubit': {'Frequency': 2741.309, 'Gain': 5500, "sigma": 0.01, "flattop_length": 0.02}, # 20, 20
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-11-04_CoolDown/TATQ01-Si-newPlassys-01/Q2_Q3_Q4_Q6//"},
    '3': {'Readout': {'Frequency': 6879.883, 'Gain': 5100, 'readout_length' : 10},
          'Qubit': {'Frequency': 3204.20, 'Gain': 7780, "sigma": 0.15, "flattop_length": 0.3},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ01-Si-newPlassys-01/Q2_Q3_Q4_Q6//"},
    '4': {'Readout': {'Frequency': 6965.63, 'Gain': 6500, 'readout_length' : 5},
          'Qubit': {'Frequency': 3571.54, 'Gain': 5800, "sigma": 0.5, "flattop_length":22},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ01-Si-newPlassys-01/Q2_Q3_Q4_Q6//"},
    '5': {'Readout': {'Frequency': 7092.672, 'Gain': 3500, 'readout_length' : 10},
          'Qubit': {'Frequency': 3581.93, 'Gain': 6000, "sigma": 0.5, "flattop_length": 20},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ01-Si-newPlassys-01/Q5_7p09//"},
    '6': {'Readout': {'Frequency': 7156.39, 'Gain': 5700, 'readout_length' : 10},
          'Qubit': {'Frequency': 3908.10, 'Gain': 7525, "sigma": 0.03, "flattop_length": 0.2},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ01-Si-newPlassys-01/Q2_Q3_Q4_Q6//"},
    }
############### End Can A ############################

# Readout

T1_qubitsweep = True
T1T2_params = {"qubit_swept": [2, 3, 4, 6],
               "T1_step_list": [50, 50, 50, 50], #"T1_step": 50,
               "T1_expts_list": [100, 100, 100, 100], #"T1_expts": 100,
               "T1_reps": 15,
               "T1_rounds": 20,
               "relax_delay": 5000}

T1_switchsweep = False
T1T2_switch = {"qubit_number": 2,
               "trig_buffer_end_list": [0.03],
               "outer_loop": False}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"reps": 200, 'rounds': 1,
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
            readout_length = Qubit_Parameters[str(Qubit_Pulse)]['Readout']['readout_length']

            trans_config = {
                "reps": 10000,  # this will used for all experiements below unless otherwise changed in between trials
                "pulse_style": "const",  # --Fixed
                "readout_length": readout_length,  # [us]
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
                            "Qubit_number": Qubit_Readout,
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

            if T1T2_params["T1_step_list"] != None:
                T1step = T1T2_params["T1_step_list"][i-5]
            else:
                T1step = T1T2_params["T1_step"]

            if T1T2_params["T1_expts_list"] != None:
                T1expts = T1T2_params["T1_expts_list"][i-5]
            else:
                T1expts = T1T2_params["T1_expts"]

            expt_cfg = {"start": 0,
                        "step": T1step,
                        "expts": T1expts,
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

