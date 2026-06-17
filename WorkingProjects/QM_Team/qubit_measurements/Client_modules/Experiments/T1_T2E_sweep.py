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

#### define the saving path

# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6702.75, 'Gain': 5200},
#           'Qubit': {'Frequency': 3149.3, 'Gain': 4800, "sigma": 0.3, "flattop_length": None},  # pi: 4800, pi/2: 2400,
#           'outerfoldername': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T1/",
#           'outerfoldernameT2': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T2/"},  # readout_time: 10
#
#     '2': {'Readout': {'Frequency': 6912.5, 'Gain': 2500},
#           'Qubit': {'Frequency': 2743.38, 'Gain': 6000, "sigma": 0.6, "flattop_length": None}, # pi: 6000, pi/2: 3000,
#           'outerfoldername': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T1/",
#           'outerfoldernameT2': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T2/"},  # readout_time: 15
#
#     '3': {'Readout': {'Frequency': 7113.2, 'Gain': 5000},
#           'Qubit': {'Frequency': 3025.1, 'Gain': 4380, "sigma": 0.05, "flattop_length": None},  # pi: 4380, pi/2: 2200,
#           'outerfoldername': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T1/",
#           'outerfoldernameT2': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T2/"},  # readout_time: 10
#
#     '4': {'Readout': {'Frequency': 7256.15, 'Gain': 5000},
#           'Qubit': {'Frequency': 2848.28, 'Gain': 5625, "sigma": 0.75, "flattop_length": None},  # pi: 5625, pi/2: 2650,
#           'outerfoldername': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T1/",
#           'outerfoldernameT2': "Z:/t1Team/Data/2026-02-22_BFF_cooldown/TATP03-01/RFSOC/T2/"}  # readout_time: 20
# }

Qubit_Parameters = {
    "1": {"Readout": {"Frequency": 6649.4, "Gain": 6000},
          "Qubit": {"Frequency": 1724.135, "Gain": 10000, "sigma": 2.2, "flattop_length": None},
          "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q1/",
          "outerfoldernameT2": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q1/"},

    "2": {"Readout": {"Frequency": 6767, "Gain": 10000},
          "Qubit": {"Frequency": 1862.65, "Gain": 18000, "sigma": 2.2, "flattop_length": None},  # 0.03 sigma
          "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q2/",
          "outerfoldernameT2": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q2/"},

    "3": {"Readout": {"Frequency": 6853.4, "Gain": 9000},
          "Qubit": {"Frequency": 2106.9739, "Gain": 4200, "sigma": 1.5, "flattop_length": None},
          "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q3/",
          "outerfoldernameT2": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q3/"},

    "4": {"Readout": {"Frequency": 6946.126, "Gain": 6000},
          "Qubit": {"Frequency": 2248.97, "Gain": 1218, "sigma": 1, "flattop_length": None},
          "outerfoldername": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q4/",
          "outerfoldernameT2": "Z:/t1Team/Data/2026-06-08_BFG_cooldown/Device 4 KOH stats/RFSOC/Q4/"},
}

T1_qubitsweep = False
T1_T2E_sweep = True

T1T2_params = {"qubit_swept": [1,2,3,4],
               "T1_step_list": [110, 10, 10, 70],
               "T1_expts_list": [100,100,100,100],
               "T1_reps_list": [15,15,15,15],
               "T1_rounds_list": [15,15,15,15],
               "T2E_max_list": [1550,1550,1550,1550],
               "T2E_expts_list": [100,100,100,100],
               "T2E_reps_list": [20,20,20,20],
               "T2E_rounds_list": [20,20,20,20],
               "pi2_gain_list": [5000,9000,2100,609],
               "T1_relax_delay": [11000,1000,1000,7000],
               "T2E_relax_delay": [11000,1000,1000,7000]}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"reps": 200,
                         'rounds': 5,
                         'relax_delay': 5000,}
repetition_number = 100000


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

if T1_T2E_sweep:
    for rep in range(repetition_number):
        for idx, i in enumerate(T1T2_params["qubit_swept"]):
            from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import BaseConfig

            Qubit_Readout = i
            Qubit_Pulse = i
            outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']
            outerFolderT2 = Qubit_Parameters[str(Qubit_Readout)]['outerfoldernameT2']

            cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
            resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
            qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
            qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']
            qubit_sigma = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['sigma']
            qubit_flattop = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['flattop_length']

            trans_config = {
                "reps": 10000,
                "pulse_style": "const",
                "readout_length": 5,
                "pulse_gain": cavity_gain,
                "pulse_freq": resonator_frequency_center,
                "TransSpan": 1,
                "TransNumPoints": 61,
                "cav_relax_delay": 30
            }

            config = BaseConfig | trans_config
            config["FF_Qubits"] = FF_Qubits
            config["cavity_min"] = True

            ARabi_config = {
                'gain_start': 0,
                "gain_end": qubit_gain,
                'gainNumPoints': 3,
                "reps": Amplitude_Rabi_params['reps'],
                "rounds": Amplitude_Rabi_params['rounds'],
                "Qubit_number": Qubit_Readout,
                "sigma": qubit_sigma,
                "f_ge": qubit_frequency_center,
                "relax_delay": 3000,
                "flattop_length": qubit_flattop
            }
            config = config | ARabi_config

            iAmpRabi = AmplitudeRabiFF_N(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                         outerFolder=outerFolder)
            dAmpRabi = AmplitudeRabiFF_N.acquire(iAmpRabi)
            rotation_angle, min_max = AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=False, figNum=2)
            AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
            AmplitudeRabiFF_N.save_config(iAmpRabi)
            config["rotation_angle"] = rotation_angle
            config["min_max"] = min_max

            T1step = T1T2_params["T1_step_list"][idx]
            T1expts = T1T2_params["T1_expts_list"][idx]
            T1reps = T1T2_params["T1_reps_list"][idx]
            T1rounds = T1T2_params["T1_rounds_list"][idx]
            T1relax = T1T2_params["T1_relax_delay"][idx]

            expt_cfg = {
                "start": 0,
                "step": T1step,
                "expts": T1expts,
                "reps": T1reps,
                "rounds": T1rounds,
                "pi_gain": qubit_gain,
                "relax_delay": T1relax,
                "f_ge": qubit_frequency_center,
                "Qubit_number": Qubit_Readout,
                "sigma": qubit_sigma,
                "flattop_length": qubit_flattop
            }
            config = config | expt_cfg

            iT1 = T1FF(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
            dT1 = T1FF.acquire(iT1)
            T1FF.display(iT1, dT1, plotDisp=False, figNum=2)
            T1FF.save_data(iT1, dT1)
            T1FF.save_config(iT1)

            time.sleep(10)
            soc.reset_gens()

            T2Emax = T1T2_params["T2E_max_list"][idx]
            T2Eexpts = T1T2_params["T2E_expts_list"][idx]
            T2Ereps = T1T2_params["T2E_reps_list"][idx]
            T2Erounds = T1T2_params["T2E_rounds_list"][idx]
            qubit_gain_pi2 = T1T2_params["pi2_gain_list"][idx]
            T2Erelax = T1T2_params["T2E_relax_delay"][idx]

            num_pulses = 1
            int_steps = T2Emax // (0.00232515 * (num_pulses + 1) * T2Eexpts)

            T2E_cfg = {
                "start": 0,
                "step": 0.00232515 * (num_pulses + 1) * int_steps,
                "expts": T2Eexpts,
                "reps": T2Ereps,
                "rounds": T2Erounds,
                "pi_gain": qubit_gain,
                "pi2_gain": qubit_gain_pi2,
                "relax_delay": T2Erelax,
                "f_ge": qubit_frequency_center,
                "num_pi_pulses": num_pulses,
                "sigma": qubit_sigma,
                "flattop_length": qubit_flattop,
                "Qubit_number": Qubit_Readout
            }

            if int_steps == 0:
                print('Step size is 0! need to increase total time or decrease experiments')
            else:
                config = config | T2E_cfg
                iT2E = T2EMUX(path="T2E", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolderT2)
                dT2E = T2EMUX.acquire(iT2E)
                T2EMUX.display(iT2E, dT2E, plotDisp=False, figNum=2)
                T2EMUX.save_data(iT2E, dT2E)
                T2EMUX.save_config(iT2E)

            time.sleep(10)
            soc.reset_gens()
