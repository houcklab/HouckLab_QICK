# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2CPMG import T2ECPMG


soc, soccfg = makeProxy_RFSOC_10()

#### define the saving path

#Readout Qubit Params
############### Start Can A ############################
Qubit_Parameters = {
    '3': {'Readout': {'Frequency': 6879.79, 'Gain': 5750},
          'Qubit': {'Frequency': 3204.30, 'Gain': 7713, "sigma": 0.15, "flattop_length": 0.3},  # pi = 7713, pi/2 = 3795
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ01-Si-newPlassys-01/T2E_Q3_Q4_Q5_Q6//"},
    '4': {'Readout': {'Frequency': 6965.58, 'Gain': 5500},
          'Qubit': {'Frequency': 3571.57, 'Gain': 5330, "sigma": 0.5, "flattop_length":22},  # pi = 5330, pi/2 = 2582
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ01-Si-newPlassys-01/T2E_Q3_Q4_Q5_Q6//"},
    '5': {'Readout': {'Frequency': 7092.65, 'Gain': 5000},
          'Qubit': {'Frequency': 3581.64, 'Gain': 6002, "sigma": 0.5, "flattop_length": 5}, # pi = 6002, pi/2 = 3004
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ01-Si-newPlassys-01/T2E_Q3_Q4_Q5_Q6//"},
    '6': {'Readout': {'Frequency': 7156.40, 'Gain': 5350},
          'Qubit': {'Frequency': 3908.20, 'Gain': 6581, "sigma": 0.03, "flattop_length": 0.2}, # pi = 6581, pi/2 = 3313
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-11-04_CoolDown/TATQ01-Si-newPlassys-01/T2E_Q3_Q4_Q5_Q6//"},
    }
############### End Can A ############################
# Readout
#Qubit_Readout = [1, 2]
#Qubit_Pulse = [1, 2]
#outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

# RunAmplitudeRabi = False
# Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
#                          "reps": 3000, 'rounds': 1,
#                          'relax_delay': 5000}

RunT2 = False
T1T2_params = {"T1_step": 50, "T1_expts": 100, "T1_reps": 20, "T1_rounds": 25,
               "T2_step": 2, "T2_expts": 50, "T2_reps": 10, "T2_rounds": 10, "freq_shift": 0.1,
               "relax_delay": 3000,"sigma": 0.03,
               'repetitions': 1000}

RunT2E = False
T2E_params = {"T2_max_us": 1500, "T2_expts": 70, "T2_reps": 20, "T2_rounds": 30, "freq_shift": 0.0,
               "relax_delay": 5000,#need odd number of pulses
               "pi2_gain": 3515.5,
              'repetitions': 1000,
              # "num_pulses": [1, 3, 9, 21, 41, 81, 161],
              # 'T2_max_us_list': [800, 1000, 1500, 1700, 2000, 2000, 2000]
              "num_pulses": [1],
              'T2_max_us_list': [800]
              }

RunT2CPMG = True
T2CPMG_params = {"qubit_swept": [3, 4, 5, 6], "T2_max_us": 3000, "T2_expts": 75, "T2_reps": 3, "T2_rounds": 100, "freq_shift": 0.0,
                 "relax_delay": 5000,
                 "pi2_gain_list": [3795, 2582, 3004, 3313],
                 'repetitions': 1000,
                 "num_pulses": [1],
                 'T2_max_us_list': [[2000], [2000], [2000], [2000]]
                 }

if RunT2CPMG:
    for r in range(T2E_params["repetitions"]):

        for ind, num_p in enumerate(T2CPMG_params["num_pulses"]):

            for i, qubit in enumerate(T2CPMG_params["qubit_swept"]):
                from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import BaseConfig

                Qubit_Readout = qubit
                Qubit_Pulse = qubit
                outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

                cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
                resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
                qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
                qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']

                qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
                qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']

                trans_config = {
                    "reps": 15000,
                    # this will used for all experiements below unless otherwise changed in between trials
                    "pulse_style": "const",  # --Fixed
                    "readout_length": 10,  # [us]
                    "pulse_gain": cavity_gain,  # [DAC units]
                    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
                    "TransSpan": 1,  ### MHz, span will be center+/- this parameter
                    "TransNumPoints": 61,  ### number of points in the transmission frequecny
                    "cav_relax_delay": 30
                }

                UpdateConfig = trans_config
                config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
                config["FF_Qubits"] = FF_Qubits

                #### update the qubit and cavity attenuation
                # cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

                cavity_min = True
                config["cavity_min"] = cavity_min  # look for dip, not peak, perform the cavity transmission experiment

                Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                                         "reps": 100,
                                         'rounds': 1,
                                         'relax_delay': 5000}

                number_of_steps = 3
                num_pulses = num_p
                ARabi_config = {'gain_start': 0, "gain_end": qubit_gain,
                                'gainNumPoints': number_of_steps,
                                "reps": Amplitude_Rabi_params['reps'],
                                "rounds": Amplitude_Rabi_params['rounds'],
                                "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
                                "relax_delay": 5000,
                                "flattop_length": qubit_flattop,
                                "num_pi_pulses": num_p}

                if T2CPMG_params["T2_max_us_list"] != None:
                    max_t2 = T2CPMG_params["T2_max_us_list"][i][ind]
                else:
                    max_t2 = T2CPMG_params["T2_max_us"]

                if T2CPMG_params["pi2_gain_list"] != None:
                    qubit_gain_pi2 = T2CPMG_params["pi2_gain_list"][i]
                else:
                    qubit_gain_pi2 = T2CPMG_params["pi2_gain"]

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
                           "pi2_gain": qubit_gain_pi2, "relax_delay": T2CPMG_params["relax_delay"],
                           'f_ge': qubit_frequency_center + T2CPMG_params["freq_shift"],
                           "num_pi_pulses": num_p,
                           "flattop_length": qubit_flattop,
                            "Qubit_number": Qubit_Readout
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

                config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
                iAmpRabi = AmplitudeRabiFF_N(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                             outerFolder=outerFolder)
                dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
                rotation_angle, min_max = AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=False, figNum=2)
                AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
                AmplitudeRabiFF_N.save_config(iAmpRabi)
                config["rotation_angle"] = rotation_angle
                config["min_max"] = min_max

                time.sleep(10)
                soc.reset_gens()