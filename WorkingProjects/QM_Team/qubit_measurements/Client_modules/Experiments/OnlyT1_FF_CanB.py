# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF import AmplitudeRabiFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF_NoUpdate import T1FF_N

soc, soccfg = makeProxy()

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 7074.262, 'Gain': 3300},
          'Qubit': {'Frequency': 5343.40, 'Gain': 6600, "sigma": 0.1, "flattop_length": 0.75}, #pi: 6600, pi/2: 3300
          'outerfoldernameT1': "Z:/t1Team/Data/2024-12-22_cooldown/TATCR02_Siegert_02/T1/",
          'outerfoldernameT2E': "Z:/t1Team/Data/2024-12-22_cooldown/TATCR02_Siegert_02/T2E/"},
    '2': {'Readout': {'Frequency': 7191.452, 'Gain': 3700},
          'Qubit': {'Frequency': 5179.30, 'Gain': 8100, "sigma": 0.1, "flattop_length": 0.5}, #pi: 8100, pi/2: 4050
          'outerfoldernameT1': "Z:/t1Team/Data/2024-12-22_CoolDown/TATCR02_Siegert_02/T1/",
          'outerfoldernameT2E': "Z:/t1Team/Data/2024-12-22_cooldown/TATCR02_Siegert_02/T2E/"},
    '3': {'Readout': {'Frequency': 7270.524, 'Gain': 4000},
          'Qubit': {'Frequency': 4685.7, 'Gain': 8000, "sigma": 0.1, "flattop_length": 0.75}, #pi: 8000, pi/2: 4000
          'outerfoldernameT1': "Z:/t1Team/Data/2024-12-22_CoolDown/TATCR02_Siegert_02/T1/",
          'outerfoldernameT2E': "Z:/t1Team/Data/2024-12-22_cooldown/TATCR02_Siegert_02/T2E/"},
    '4': {'Readout': {'Frequency': 7371.936, 'Gain': 4400},
          'Qubit': {'Frequency': 4351.38, 'Gain': 7600, "sigma": 0.05, "flattop_length": 0.1}, #pi: 7600, pi/2: 3800
          'outerfoldernameT1': "Z:/t1Team/Data/2024-12-22_CoolDown/TATCR02_Siegert_02/T1/",
          'outerfoldernameT2E': "Z:/t1Team/Data/2024-12-22_cooldown/TATCR02_Siegert_02/T2E/"}
    }


T1_T2Equbitsweepswitch = True
T1T2E_params = {"qubit_swept": [1, 2, 3, 4],
                "T1_step_list": [15, 15, 15, 15],
                "T1_expts_list": [100, 100, 100, 100],
                "T1_reps_list": [20, 20, 20, 20],
                "T1_rounds_list": [20, 20, 20, 20],
                "T2_max_us_list": [500, 500, 500, 500],
                "T2_expts_list": [50, 50, 50, 50],
                "T2_reps_list": [20, 20, 20, 20],
                "T2_rounds_list": [20, 20, 20, 20],
                "pi2_gain_list": [3300, 4050, 4000, 3800],
                "freq_shift": 0.0,
                "num_pulses_list": [1, 3],
                "relax_delay": 1000}

Amplitude_Rabi_params = {"repsT1": 200,
                         "roundsT1": 2,
                         "repsT2E": 500,
                         "roundsT2E": 5,
                         "relax_delay": 1000}

repetition_number = 10000

if T1_T2Equbitsweepswitch:
    for rep in range(repetition_number):
        for i in T1T2E_params["qubit_swept"]:
            from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import BaseConfig

            Qubit_Readout = i
            Qubit_Pulse = i
            outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldernameT1']

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
            n_filler = 0
            ARabi_config = {'gain_start': 0, "gain_end": qubit_gain,
                            'gainNumPoints': number_of_steps,
                            "reps": Amplitude_Rabi_params['repsT1'],
                            "rounds": Amplitude_Rabi_params['roundsT1'],
                            "Qubit_number": Qubit_Readout,
                            "sigma": qubit_sigma,
                            "f_ge": qubit_frequency_center,
                            "relax_delay": 1000,
                            "flattop_length": qubit_flattop,
                            "num_pi_pulses": n_filler}
            config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
            iAmpRabi = AmplitudeRabiFF_N(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                         outerFolder=outerFolder)
            dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
            rotation_angle, min_max = AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=False, figNum=2)
            AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
            AmplitudeRabiFF_N.save_config(iAmpRabi)
            config["rotation_angle"] = rotation_angle
            config["min_max"] = min_max

            if T1T2E_params["T1_step_list"] != None:
                T1step = T1T2E_params["T1_step_list"][i - 1]
            else:
                T1step = T1T2E_params["T1_step"]

            if T1T2E_params["T1_expts_list"] != None:
                T1expts = T1T2E_params["T1_expts_list"][i - 1]
            else:
                T1expts = T1T2E_params["T1_expts"]

            if T1T2E_params["T1_reps_list"] != None:
                T1reps = T1T2E_params["T1_reps_list"][i - 1]
            else:
                T1reps = T1T2E_params["T1_reps"]

            if T1T2E_params["T1_rounds_list"] != None:
                T1rounds = T1T2E_params["T1_rounds_list"][i - 1]
            else:
                T1rounds = T1T2E_params["T1_rounds"]

            expt_cfg = {"start": 0,
                        "step": T1step,
                        "expts": T1expts,
                        "reps": T1reps,
                        "rounds": T1rounds,
                        "pi_gain": qubit_gain,
                        "relax_delay": T1T2E_params["relax_delay"],
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

            for n in range(len(T1T2E_params["num_pulses_list"])):
                num_pulses = T1T2E_params["num_pulses_list"][n]

                from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import BaseConfig
                outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldernameT2E']

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
                                "reps": Amplitude_Rabi_params['repsT2E'],
                                "rounds": Amplitude_Rabi_params['roundsT2E'],
                                "sigma": qubit_sigma,
                                "f_ge": qubit_frequency_center,
                                "relax_delay": 1000,
                                "flattop_length": qubit_flattop,
                                "num_pi_pulses": num_pulses}

                config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
                iAmpRabi = AmplitudeRabiFF_N(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                             outerFolder=outerFolder)
                dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
                rotation_angle, min_max = AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=False, figNum=2)
                AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
                AmplitudeRabiFF_N.save_config(iAmpRabi)
                config["rotation_angle"] = rotation_angle
                config["min_max"] = min_max

                if T1T2E_params["T2_max_us_list"] != None:
                    max_t2 = T1T2E_params["T2_max_us_list"][i - 1]
                else:
                    max_t2 = T1T2E_params["T2_max_us"]

                if T1T2E_params["T2_expts_list"] != None:
                    T2expts = T1T2E_params["T2_expts_list"][i - 1]
                else:
                    T2expts = T1T2E_params["T2_expts"]

                if T1T2E_params["T2_reps_list"] != None:
                    T2reps = T1T2E_params["T2_reps_list"][i - 1]
                else:
                    T2reps = T1T2E_params["T2_reps"]

                if T1T2E_params["T2_rounds_list"] != None:
                    T2rounds = T1T2E_params["T2_rounds_list"][i - 1]
                else:
                    T2rounds = T1T2E_params["T2_rounds"]

                if T1T2E_params["pi2_gain_list"] != None:
                    qubit_gain_pi2 = T1T2E_params["pi2_gain_list"][i - 1]
                else:
                    qubit_gain_pi2 = T1T2E_params["pi2_gain"]

                int_steps = max_t2 // (0.00232515 * (num_pulses + 1) * T2expts)
                T2E_cfg = {"start": 0,
                           "step": 0.00232515 * (num_pulses + 1) * int_steps,
                           "expts": T2expts,
                           "reps": T2reps,
                           "rounds": T2rounds,
                           "pi_gain": qubit_gain,
                           "sigma": qubit_sigma,
                           "pi2_gain": qubit_gain_pi2,
                           "relax_delay": T1T2E_params["relax_delay"],
                           'f_ge': qubit_frequency_center + T1T2E_params["freq_shift"],
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