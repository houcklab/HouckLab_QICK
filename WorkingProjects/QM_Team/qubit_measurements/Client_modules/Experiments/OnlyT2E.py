# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2CPMG import T2ECPMG


soc, soccfg = makeProxy()

#### define the saving path

#Readout Qubit Params
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6730.58, 'Gain': int(6500 / 1.6)},
          'Qubit': {'Frequency': 3124, 'Gain': int(9000)},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-08-09_cooldown/TATQ01-Si_02/Q1_6p730//"},
    '2': {'Readout': {'Frequency': 6843.05, 'Gain': 4500},
          # 'Qubit': {'Frequency': 3108.16, 'Gain': 450}, #0.4 sigma
          # 'Qubit': {'Frequency': 3108.16, 'Gain': 6400, "sigma": 0.01, "flattop_length": 0.04}, #0.03 sigma
          # 'Qubit': {'Frequency': 3108.16, 'Gain': 7907, "sigma": 0.01, "flattop_length": 0.06},  # 0.03 sigma
          'Qubit': {'Frequency': 3108.3, 'Gain': 5185, "sigma": 0.01, "flattop_length": 0.06}, #0.03 sigma

          'QubitPi2_gain': 280,
          'QubitPi2_gain': 3200,
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-08-09_cooldown/TATQ01-Si_02/Q2_6p843//T2vsN//"},
    '3': {'Readout': {'Frequency': 6932.3, 'Gain': 5000},
          'Qubit': {'Frequency': 3437.6, 'Gain': 4000},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-08-09_cooldown/TATQ01-Si_02/Q3_6p9325//"},
    '4': {'Readout': {'Frequency': 7214.9, 'Gain': 6000},
          'Qubit': {'Frequency': 3824.2, 'Gain': 3900},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-08-09_cooldown/TATQ01-Si_02/Q4_7p21//"},
    }
# Readout
Qubit_Readout = 2
Qubit_Pulse = 2
outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "reps": 3000, 'rounds': 1,
                         'relax_delay': 5000,}

RunT2 = False
T1T2_params = {"T1_step": 50, "T1_expts": 100, "T1_reps": 20, "T1_rounds": 25,
               "T2_step": 2, "T2_expts": 50, "T2_reps": 10, "T2_rounds": 10, "freq_shift": 0.1,
               "relax_delay": 3000,"sigma": 0.03,
               'repetitions': 1000}

RunT2E = False
T2E_params = {"T2_max_us": 1500, "T2_expts": 70, "T2_reps": 20, "T2_rounds": 30, "freq_shift": 0.0,
               "relax_delay": 5000,#need odd number of pulses
               "pi2_gain": 2598,
              'repetitions': 1000,
              # "num_pulses": [1, 3, 9, 21, 41, 81, 161],
              # 'T2_max_us_list': [800, 1000, 1500, 1700, 2000, 2000, 2000]
              "num_pulses": [1, 161],
              'T2_max_us_list': [800, 2000]
              }

RunT2CPMG = True
T2CPMG_params = {"T2_max_us": 1500, "T2_expts": 70, "T2_reps": 20, "T2_rounds": 30, "freq_shift": 0.0,
               "relax_delay": 5000,#need odd number of pulses
               "pi2_gain": 2568,
              'repetitions': 1000,
              "num_pulses": [1, 3, 9, 21, 41, 81, 161],
              'T2_max_us_list': [800, 1000, 1500, 1700, 2000, 2000, 2000],
                'T2_max_us_list': [600, 800, 1000, 1200, 1300, 1500, 1600] #1000, 1500, 1700, 2000, 2000, 2000],
                 }

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
    "TransSpan": 0.6,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 61,  ### number of points in the transmission frequecny
    "cav_relax_delay": 30
}

UpdateConfig = trans_config
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)


cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak
# perform the cavity transmission experiment
#


if RunAmplitudeRabi:
    number_of_steps = 3
    ARabi_config = {'gain_start': 0, "gain_end": qubit_gain,
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
    rotation_angle, min_max = AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    print(rotation_angle, min_max)
    AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
    AmplitudeRabiFF_N.save_config(iAmpRabi)


if RunT2:
    T2R_cfg = {"start": 0, "step": T1T2_params["T2_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
               "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
               "pi_gain": qubit_gain, "sigma": T1T2_params["sigma"],
               "pi2_gain": qubit_gain // 2, "relax_delay": T1T2_params["relax_delay"],
               'f_ge': qubit_frequency_center + T1T2_params["freq_shift"]
               }
    config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2R.acquire(iT2R)
    T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2R.save_data(iT2R, dT2R)
    T2R.save_config(iT2R)


if RunT2E:
    for r in range(T2E_params["repetitions"]):
        number_of_steps = 3
        ARabi_config = {'gain_start': 0, "gain_end": qubit_gain,
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
        rotation_angle, min_max = AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=False, figNum=2)
        AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF_N.save_config(iAmpRabi)
        config["rotation_angle"] = rotation_angle
        config["min_max"] = min_max
        for ind, num_p in enumerate(T2E_params["num_pulses"]):
            if T2E_params["pi2_gain"] == False:
                qubit_gain_pi2 = qubit_gain // 2
            else:
                qubit_gain_pi2 = T2E_params["pi2_gain"]
            num_pulses = num_p
            if T2E_params["T2_max_us_list"] != None:
                max_t2 = T2E_params["T2_max_us_list"][ind]
            else:
                max_t2 = T2E_params["T2_max_us"]
            int_steps = max_t2 // (0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"])
            T2E_cfg = {"start": 0, "step": 0.00232515 * (num_pulses + 1) * int_steps,
                       "expts": T2E_params["T2_expts"], "reps": T2E_params["T2_reps"], "rounds": T2E_params["T2_rounds"],
                       "pi_gain": qubit_gain, "sigma": qubit_sigma,
                       "pi2_gain": qubit_gain_pi2, "relax_delay": T2E_params["relax_delay"],
                       'f_ge': qubit_frequency_center + T2E_params["freq_shift"],
                       "num_pi_pulses": num_p
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


if RunT2CPMG:
    for r in range(T2E_params["repetitions"]):
        for ind, num_p in enumerate(T2CPMG_params["num_pulses"]):
            number_of_steps = 3
            ARabi_config = {'gain_start': 0, "gain_end": qubit_gain,
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
            rotation_angle, min_max = AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=False, figNum=2)
            AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
            AmplitudeRabiFF_N.save_config(iAmpRabi)
            config["rotation_angle"] = rotation_angle
            config["min_max"] = min_max

            if T2CPMG_params["pi2_gain"] == False:
                qubit_gain_pi2 = qubit_gain // 2
            else:
                qubit_gain_pi2 = T2CPMG_params["pi2_gain"]
            num_pulses = num_p
            if T2CPMG_params["T2_max_us_list"] != None:
                max_t2 = T2CPMG_params["T2_max_us_list"][ind]
            else:
                max_t2 = T2CPMG_params["T2_max_us"]

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
                       "flattop_length": qubit_flattop
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

                time.sleep(10)
                soc.reset_gens()

