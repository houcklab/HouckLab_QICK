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
############### Start Can D ############################
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6674.95, 'Gain': 12600},
#           'Qubit': {'Frequency': 2972.879, 'Gain': 5075, "sigma": 0.4, "flattop_length": 10},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername':"Z:/t1Team/Data/2024-11-06_BFF_cooldown/Q1_Q2_Q4_Q5/"},
#     '2': {'Readout': {'Frequency': 6818.05, 'Gain': 12600},
#           'Qubit': {'Frequency': 3288.60, 'Gain': 10350, "sigma": 0.4, "flattop_length": 20},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername':"Z:/t1Team/Data/2024-11-06_BFF_cooldown/Q1_Q2_Q4_Q5/"},
#     '3': {'Readout': {'Frequency': 6898.3, 'Gain': 12100},
#           'Qubit': {'Frequency': 3370.4335, 'Gain': 13000, "sigma": 0.4, "flattop_length": 25},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-11-06_BFF_cooldown/Q1_Q2_Q3_Q4_Q5_Q6/"},
#     '4': {'Readout': {'Frequency': 6966.450, 'Gain': 12400},
#           'Qubit': {'Frequency': 3673.67, 'Gain': 1580, "sigma": 0.4, "flattop_length": 2}, #3000
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-11-06_BFF_cooldown/Q1_Q2_Q4_Q5/"},
#     '5': {'Readout': {'Frequency': 7101.473, 'Gain': 12100},
#           'Qubit': {'Frequency': 3677.465, 'Gain': 4750, "sigma": 0.4, "flattop_length": 10},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-11-06_BFF_cooldown/Q1_Q2_Q4_Q5/"},
#     '6': {'Readout': {'Frequency': 7142.473, 'Gain': 15000},
#           'Qubit': {'Frequency': 3973.550, 'Gain': 5750, "sigma": 0.4, "flattop_length": 25},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-11-06_BFF_cooldown/Q1_Q2_Q3_Q4_Q5_Q6/"},
#     }
# ############### End Can D ############################

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6702.75, 'Gain': 5200},
          'Qubit': {'Frequency': 3149.3, 'Gain': 4800, "sigma": 0.3, "flattop_length": None},  # pi: 4800, pi/2: 2400,
          'outerfoldername': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T1/",
          'outerfoldernameT2': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T2/"},  # readout_time: 10

    '2': {'Readout': {'Frequency': 6912.5, 'Gain': 2500},
          'Qubit': {'Frequency': 2743.38, 'Gain': 6000, "sigma": 0.6, "flattop_length": None}, # pi: 6000, pi/2: 3000,
          'outerfoldername': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T1/",
          'outerfoldernameT2': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T2/"},  # readout_time: 15

    '3': {'Readout': {'Frequency': 7113.2, 'Gain': 5000},
          'Qubit': {'Frequency': 3025.1, 'Gain': 4380, "sigma": 0.05, "flattop_length": None},  # pi: 4380, pi/2: 2200,
          'outerfoldername': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T1/",
          'outerfoldernameT2': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T2/"},  # readout_time: 10

    '4': {'Readout': {'Frequency': 7256.15, 'Gain': 5000},
          'Qubit': {'Frequency': 2848.28, 'Gain': 5625, "sigma": 0.75, "flattop_length": None},  # pi: 5625, pi/2: 2650,
          'outerfoldername': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T1/",
          'outerfoldernameT2': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T2/"}  # readout_time: 20
}

T1_qubitsweep = True
T1T2_params = {"qubit_swept": [1, 2, 3, 4],
               "T1_step_list": [40, 40, 40, 40],
               "T1_expts_list": [100, 100, 100, 100],
               "T1_reps_list": [15, 15, 15, 15],
               "T1_rounds_list": [15, 15, 15, 15],
               "relax_delay": 3000}

T1_switchsweep = False
T1T2_switch = {"qubit_number": 2,
               "trig_buffer_end_list": [0.03],
               "outer_loop": False}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"reps": 200,
                         'rounds': 5,
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
                "readout_length": 5,  # [us]
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
                            "Qubit_number": Qubit_Readout,
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

            if T1T2_params["T1_step_list"] != None:
                T1step = T1T2_params["T1_step_list"][i-1]
            else:
                T1step = T1T2_params["T1_step"]

            if T1T2_params["T1_expts_list"] != None:
                T1expts = T1T2_params["T1_expts_list"][i-1]
            else:
                T1expts = T1T2_params["T1_expts"]

            if T1T2_params["T1_reps_list"] != None:
                T1reps = T1T2_params["T1_reps_list"][i-1]
            else:
                T1reps = T1T2_params["T1_reps"]

            if T1T2_params["T1_rounds_list"] != None:
                T1rounds = T1T2_params["T1_rounds_list"][i-1]
            else:
                T1rounds = T1T2_params["T1_rounds"]

            expt_cfg = {"start": 0,
                        "step": T1step,
                        "expts": T1expts,
                        "reps": T1reps,
                        "rounds": T1rounds, "pi_gain": qubit_gain,
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
                "readout_length": 5,  # [us]
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

