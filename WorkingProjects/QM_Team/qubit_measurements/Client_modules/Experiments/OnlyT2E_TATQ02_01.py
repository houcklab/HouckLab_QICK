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
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX

soc, soccfg = makeProxy_RFSOC_119()

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6600.30, 'Gain': 4000},
          'Qubit': {'Frequency': 2943.12, 'Gain': 6250, "sigma": 0.15, "flattop_length": 0.4}, #3125
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-11-04_CoolDown/TATQ02-Si-01/T2E_Q1_Q4_Q5_Q6/"},
    '2': {'Readout': {'Frequency': 6712.7, 'Gain': 3700},
          'Qubit': {'Frequency': 3312.544, 'Gain': 10000, "sigma": 0.4, "flattop_length": 80},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ02-Si-01/T2E_Q1_Q4_Q5_Q6/"},
    '3': {'Readout': {'Frequency': 6862.26, 'Gain': 3000},
          'Qubit': {'Frequency': 3192.10, 'Gain': 7600, "sigma": 0.4, "flattop_length": 50},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ02-Si-01/T2E_Q1_Q4_Q5_Q6/"},
    '4': {'Readout': {'Frequency': 6941.53, 'Gain': 2900},
          'Qubit': {'Frequency': 3655.40, 'Gain': 7140, "sigma": 0.02, "flattop_length": 0.1}, #3570
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ02-Si-01/T2E_Q1_Q4_Q5_Q6/"},
    '5': {'Readout': {'Frequency': 7101.8, 'Gain': 3800},
          'Qubit': {'Frequency': 3660.43, 'Gain': 8600, "sigma": 0.02, "flattop_length": 0.6}, #8600
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ02-Si-01/T2E_Q1_Q4_Q5_Q6/"},
    '6': {'Readout': {'Frequency': 7190.186, 'Gain': 3800},
          'Qubit': {'Frequency': 3496.27, 'Gain': 8820, "sigma": 0.1, "flattop_length": 1.0},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ02-Si-01/T2E_Q1_Q4_Q5_Q6/"},
    }

T2_qubitsweep = True
T1_qubitsweep = False

T2E_params = {"qubit_swept": [1, 4, 5, 6],
               "T2_max_us_list": [400, 1, 1, 200, 800, 400],
               "T2_expts_list": [100, 1, 1, 100, 200, 100],
               "T2_reps_list": [15, 1, 1, 10, 20, 20],
               "T2_rounds_list": [15, 1, 1, 10, 20, 20],
               "pi2_gain_list": [3125, 1, 1, 3570, 4300, 4410],
               "freq_shift": 0.0,
               "num_pulses": 1,
               "relax_delay": 2000}

RunAmplitudeRabi = True
Amplitude_Rabi_params = {"reps": 100, #200
                         'rounds': 10,
                         'relax_delay': 5000}
repetition_number = 10000

if T2_qubitsweep:
    for r in range(repetition_number):
        for i in T2E_params["qubit_swept"]:

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
                "readout_length": 15,  # [us]
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
            ARabi_config = {'gain_start': 0,
                            "gain_end": qubit_gain,
                            'gainNumPoints': number_of_steps,
                            "Qubit_number": Qubit_Readout,
                            "reps": Amplitude_Rabi_params['reps'],
                            "rounds": Amplitude_Rabi_params['rounds'],
                            "sigma": qubit_sigma,
                            "f_ge": qubit_frequency_center,
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

            num_pulses = T2E_params["num_pulses"]

            if T2E_params["T2_max_us_list"] != None:
                max_t2 = T2E_params["T2_max_us_list"][i - 1]
            else:
                max_t2 = T2E_params["T2_max_us"]

            if T2E_params["T2_expts_list"] != None:
                T2expts = T2E_params["T2_expts_list"][i - 1]
            else:
                T2expts = T2E_params["T2_expts"]

            if T2E_params["T2_reps_list"] != None:
                T2reps = T2E_params["T2_reps_list"][i - 1]
            else:
                T2reps = T2E_params["T2_reps"]

            if T2E_params["T2_rounds_list"] != None:
                T2rounds = T2E_params["T2_rounds_list"][i - 1]
            else:
                T2rounds = T2E_params["T2_rounds"]

            if T2E_params["pi2_gain_list"] != None:
                qubit_gain_pi2 = T2E_params["pi2_gain_list"][i - 1]
            else:
                qubit_gain_pi2 = T2E_params["pi2_gain"]

            int_steps = max_t2 // (0.00232515 * (num_pulses + 1) * T2expts)
            T2E_cfg = {"start": 0,
                       "step": 0.00232515 * (num_pulses + 1) * int_steps,
                       "expts": T2expts,
                       "reps": T2reps,
                       "rounds": T2rounds,
                       "pi_gain": qubit_gain,
                       "sigma": qubit_sigma,
                       "pi2_gain": qubit_gain_pi2,
                       "relax_delay": T2E_params["relax_delay"],
                       'f_ge': qubit_frequency_center + T2E_params["freq_shift"],
                       "num_pi_pulses": num_pulses,
                       "Qubit_number": Qubit_Readout
                       }

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
