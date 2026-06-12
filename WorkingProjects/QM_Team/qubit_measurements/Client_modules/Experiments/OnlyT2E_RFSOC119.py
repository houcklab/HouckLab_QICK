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
    '1': {'Readout': {'Frequency': 7084.36, 'Gain': 1000},
          'Qubit': {'Frequency': 4841.69, 'Gain': 7800, "sigma": 0.05, "flattop_length": 0.1}, # pi = 7800, pi/2 = 3900
          'outerfoldername': "Z:/t1Team/Data/2024-12-22_cooldown/TATCR02_Topsil_01/T2E/"},
    '2': {'Readout': {'Frequency': 7197.9, 'Gain': 1200},
          'Qubit': {'Frequency': 4605.85, 'Gain': 7000, "sigma": 0.025, "flattop_length": 0.1}, # pi = 7000, pi/2 = 3500
          'outerfoldername': "Z:/t1Team/Data/2024-12-22_cooldown/TATCR02_Topsil_01/T2E/"},
    '4': {'Readout': {'Frequency': 7391.06, 'Gain': 1200},
          'Qubit': {'Frequency': 3882.6, 'Gain': 7000, "sigma": 0.01, "flattop_length": 0.05}, # pi = 7000, pi/2 = 3500
          'outerfoldername': "Z:/t1Team/Data/2024-12-22_cooldown/TATCR02_Topsil_01/T2E/"},
    }

T2_qubitsweep = True
T1_qubitsweep = False
T2E_params = {"qubit_swept": [1, 2, 4],
               "T2_max_us_list": [300, 300, 300],
               "T2_expts_list": [50, 50, 50],
               "T2_reps_list": [20, 20, 20],
               "T2_rounds_list": [20, 20, 20],
               "pi2_gain_list": [3900, 3500, 3500],
               "freq_shift": 0.0,
               "num_pulses": 1,
               "relax_delay": 1000}

RunAmplitudeRabi = True
Amplitude_Rabi_params = {"reps": 200, #200
                         'rounds': 2,
                         'relax_delay': 5000}
repetition_number = 10000

if T2_qubitsweep:
    for r in range(repetition_number):
        for i, qubit in enumerate(T2E_params["qubit_swept"]):

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
