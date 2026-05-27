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


#### define the saving path

############## Start Can D ############################
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

soc, soccfg = makeProxy_RFSOC_124()

Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6819.7, 'Gain': 4500},
#           'Qubit': {'Frequency': 3355.42, 'Gain': 2750, "sigma": 0.15, "flattop_length": None},  # pi: 4800, pi/2: 2400,
#           'outerfoldername': "Z:/t1Team/Data/2026-04-01_BFF_cooldown/TAT3DP01-02/RFSOC/T1/"},  # readout_time: 10
#
#     '4': {'Readout': {'Frequency': 7386.94, 'Gain': 5000},
#           'Qubit': {'Frequency': 2857.46, 'Gain': 2000, "sigma": 0.2, "flattop_length": None},  # pi: 2000, pi/2:
#           'outerfoldername': "Z:/t1Team/Data/2026-04-01_BFF_cooldown/TAT3DP01-02/RFSOC/T1/"}  # readout_time: 20
# }

    '1': {'Readout': {'Frequency': 6607.5, 'Gain': 10000},
          'Qubit': {'Frequency': 2131, 'Gain': 8000, "sigma": 1.8, "flattop_length": None},
          'outerfoldername': "Z:t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-03/RFSoC/Q1/"},

    '2': {'Readout': {'Frequency': 6689.14, 'Gain': 6000},
          'Qubit': {'Frequency': 2404.9, 'Gain': 6000, "sigma": 1.8, "flattop_length": 3},
          'outerfoldername': "Z:t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-03/RFSoC/Q2/"},

    '3': {'Readout': {'Frequency': 6900.4, 'Gain': 10000},
          'Qubit': {'Frequency': 3772.7, 'Gain': 6000, "sigma": 1.8, "flattop_length": 4},
          'outerfoldername': "Z:t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-03/RFSoC/Q3/"},

    '4': {'Readout': {'Frequency': 6893.27, 'Gain': 8500},
          'Qubit': {'Frequency': 2441.21, 'Gain': 4000, "sigma": 0.5, "flattop_length": 2},  #pi = 2200
          'outerfoldername': "Z:t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-03/RFSoC/Q4/"},

    '5': {'Readout': {'Frequency': 7006.91, 'Gain': 5310},
          'Qubit': {'Frequency': 2785.17, 'Gain': 5200, "sigma": 1, "flattop_length": 2},
          'outerfoldername': "Z:t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-03/RFSoC/Q5/"},

    '6': {'Readout': {'Frequency': 7073.33, 'Gain': 5000},
          'Qubit': {'Frequency': 2919.75, 'Gain': 4360, "sigma": 1.0, "flattop_length": 2}, #4360 2250 --------6220
          'outerfoldername': "Z:t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-03/RFSoC/Q6/"}
}
T1_qubitsweep = True
T1T2_params = {"qubit_swept": [6],
               "T1_step_list": [60],
               "T1_expts_list": [100],
                "T1_step": 100,
                "T1_expts": 100,
               "T1_reps": 20,
               "T1_rounds": 20,
               "relax_delay": 6000}

T1_switchsweep = False
T1T2_switch = {"qubit_number": 2,
               "trig_buffer_end_list": [0.03],
               "outer_loop": False}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"reps": 20,
                         'rounds': 20,
                         'relax_delay': 2000}

Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain": 8000, "SpecSpan": 5, "SpecNumPoints": 201,
                        "reps": 5, 'rounds': 5,
                        'Gauss': True, "sigma": 1, "gain": 8000} # False -- no pulse #If you don't see RabiAmp but with Gauss True see the qubit, the next thing to check is gain, you might not have the right pi pulse

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
            ARabi_config = {'gain_start': 0, "gain_end": qubit_gain,
                            'gainNumPoints': number_of_steps,
                            "reps": Amplitude_Rabi_params['reps'],
                            "Qubit_number": Qubit_Readout,
                            "rounds": Amplitude_Rabi_params['rounds'],
                            "sigma": qubit_sigma, "f_ge": qubit_frequency_center,
                            "relax_delay": 2000,
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

            j = T1T2_params["qubit_swept"].index(i)
            if T1T2_params["T1_step_list"] != None:
                T1step = T1T2_params["T1_step_list"][j-1]
            else:
                T1step = T1T2_params["T1_step"]

            if T1T2_params["T1_expts_list"] != None:
                T1expts = T1T2_params["T1_expts_list"][j-1]
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

# qubit spec experiment
if Run2ToneSpec:
    for rep in range(repetition_number):
        for i in T1T2_params["qubit_swept"]:
            from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import BaseConfig

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
                "TransSpan": 0.75,  ### MHz, span will be center+/- this parameter
                "TransNumPoints": 101,  ### number of points in the transmission frequecny
                "cav_relax_delay": 30
            }
            qubit_config = {
                "qubit_pulse_style": "const",
                "qubit_gain": Spec_relevant_params["qubit_gain"],
                "qubit_freq": qubit_frequency_center,
                "qubit_length": 100,
                "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
                "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],
                ### number of points in the transmission frequecny
            }
            expt_cfg = {
                "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
                "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
                "expts": qubit_config["SpecNumPoints"]
            }

            UpdateConfig = trans_config | qubit_config | expt_cfg
            config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
            config["FF_Qubits"] = FF_Qubits

            config = BaseConfig | trans_config  ### note that UpdateConfig will overwrite elements in BaseConfig
            config["FF_Qubits"] = FF_Qubits

            cavity_min = True
            config["cavity_min"] = cavity_min  # look for dip, not peak

            config["reps"] = Spec_relevant_params['reps']  # want more reps and rounds for qubit data
            config["rounds"] = Spec_relevant_params['rounds']
            config["Gauss"] = Spec_relevant_params['Gauss']

            if Spec_relevant_params['Gauss']:
                config['sigma'] = Spec_relevant_params["sigma"]
                config["qubit_gain"] = Spec_relevant_params['gain']

            Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
            data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
            QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
            QubitSpecSliceFF.save_config(Instance_specSlice)

        time.sleep(10)
        soc.reset_gens()