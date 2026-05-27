# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2CPMG import T2ECPMG


soc, soccfg = makeProxy()

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
    '1': {'Readout': {'Frequency': 6655.48, 'Gain': 6000},
          'Qubit': {'Frequency': 1917.3, 'Gain': 950, "sigma": 0.08, "flattop_length": None},  # pi: 1900, pi/2: 950,
          'outerfoldername': "Z:/t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-04/RFSoC/Q1/"},  # readout_time:
    '2': {'Readout': {'Frequency': 6754.82, 'Gain': 3000},
          'Qubit': {'Frequency': 2122.5, 'Gain': 2450, "sigma": 0.05, "flattop_length": None}, # pi: 6000, pi/2: ,
          'outerfoldername': "Z:/t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-04/RFSoC/Q2/"},  # readout_time:
    '3': {'Readout': {'Frequency': 6852.82, 'Gain': 3000},
          'Qubit': {'Frequency': 2256.17, 'Gain': 2850, "sigma": 1, "flattop_length": 10},  # pi: 2850, pi/2: 1425,
          'outerfoldername': "Z:/t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-04/RFSoC/Q3/"},  # readout_time:
    '4': {'Readout': {'Frequency':  6936.360, 'Gain': 3000},
          'Qubit': {'Frequency': 2362.62, 'Gain': 2850, "sigma": 0.5, "flattop_length": 6},  # pi: 2850, pi/2: 1425,
          'outerfoldername': "Z:/t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-04/RFSoC/Q4/"},  # readout_time:
    '5': {'Readout': {'Frequency': 7056.7, 'Gain': 3500},
          'Qubit': {'Frequency': 2520.15, 'Gain': 4550, "sigma": 0.5, "flattop_length": None},  # pi: 2850, pi/2: 1425,
          'outerfoldername': "Z:/t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-04/RFSoC/Q5/",
          'outerfoldernameT2': "Z:/t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-04/RFSoC/Q5/"},
    '6': {'Readout': {'Frequency': 7126.40, 'Gain': 15000},
          'Qubit': {'Frequency': 2720.0, 'Gain': 2850, "sigma": 0.1, "flattop_length": None},  # pi: 2850, pi/2: 1425,
          'outerfoldername': "Z:/t1Team/Data/2026-04-01_BFF_cooldown/TATQ01-3minHF-10secKOH-04/RFSoC/Q6/"}  # readout_time:
}

# Readout
Qubit_Readouts = [5]
Qubit_Pulses = [5]
pi2_gains = [250]

t1_steps = [70]
t1_expts = [100]

t2e_maxs = [2000]
t2e_expts = [100]

t2_steps = [5]
t2_expts = [200]

while True:
    for idx, Qubit_Readout in enumerate(Qubit_Readouts):
        Qubit_Pulse = Qubit_Pulses[idx]
        pi2_gain_ = pi2_gains[idx]
        t1_step = t1_steps[idx]
        t1_expt = t1_expts[idx]
        t2_step = t2_steps[idx]
        t2_expt = t2_expts[idx]
        t2e_max = t2e_maxs[idx]
        t2e_expt = t2e_expts[idx]

        outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']
        outerFolderT2 = Qubit_Parameters[str(Qubit_Readout)]['outerfoldernameT2']

        RunAmplitudeRabi = True
        Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                                 "reps": 15, 'rounds': 15,
                                 'relax_delay': 5000,}

        SingleShot = False
        SS_params = {"Shots": 1000, "Readout_Time": 10, "ADC_Offset": 0.0, "Qubit_Pulse": [Qubit_Pulse],
                     'number_of_pulses': 1, 'relax_delay': 3000}

        RunT1 = True
        RunT2 = False
        T1T2_params = {"T1_step": t1_step, "T1_expts": t1_expt, "T1_reps": 20, "T1_rounds": 20,
                       "T2_step": t2_step, "T2_expts": t2_expt, "T2_reps": 12, "T2_rounds": 12, "freq_shift": 0.0,
                       "relax_delay": 7000,"sigma": 0.03,
                       'repetitions': 1}

        RunT2E = False
        T2E_params = {"T2_max_us": t2e_max, "T2_expts": t2e_expt, "T2_reps": 12, "T2_rounds": 12, "freq_shift": 0.0,
                       "relax_delay": 3000,
                       "pi2_gain": pi2_gain_,
                      'repetitions': 1,
                      "num_pulses": [1],
                      }

        RunT2CPMG = False
        T2CPMG_params = {"T2_max_us": 1500, "T2_expts": 50, "T2_reps": 20, "T2_rounds": 50, "freq_shift": 0.0,
                       "relax_delay": 3000,#need odd number of pulses
                       "pi2_gain": 11700,
                      'repetitions': 1000,
                      "num_pulses": [0, 1, 3, 5, 7, 9, 11],
                      'T2_max_us_list': [1500, 1500, 1500, 1500, 1500, 1500, 1500],
                        # 'T2_max_us_list': [600, 800, 1000, 1200, 1300, 1500, 1600] #1000, 1500, 1700, 2000, 2000, 2000],
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
            "readout_length": 15,  # [us]
            "pulse_gain": cavity_gain,  # [DAC units]
            "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
            "TransSpan": 0.5,  ### MHz, span will be center+/- this parameter
            "TransNumPoints": 51,  ### number of points in the transmission frequecny
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

        # added by atharv 13 nov 2024
        config["Qubit_number"] = Qubit_Pulse


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
            rotation_angle, min_max = AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=False, figNum=2)
            print(rotation_angle, min_max)
            AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
            AmplitudeRabiFF_N.save_config(iAmpRabi)

        if SingleShot:
            config["shots"] = SS_params["Shots"]
            config['number_of_pulses'] = SS_params['number_of_pulses']
            Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                                soc=soc, soccfg=soccfg)
            data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
            # print(data_SingleShotProgram)
            SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)

            SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
            SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
            print('Angle: ', data_SingleShotProgram['data']['angle'][0])
            print('threshold: ', data_SingleShotProgram['data']['threshold'][0])

        if RunT1:
            for i in range(T1T2_params['repetitions']):
                expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                            "reps": T1T2_params["T1_reps"], "Qubit_number": Qubit_Readout,
                            "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain,
                            "relax_delay": T1T2_params["relax_delay"],
                            "sigma": qubit_sigma, "flattop_length": qubit_flattop,
                            "f_ge": qubit_frequency_center
                            }

                config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
                iT1 = T1FF(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
                dT1 = T1FF.acquire(iT1)
                T1FF.display(iT1, dT1, plotDisp=False, figNum=2)
                T1FF.save_data(iT1, dT1)
                T1FF.save_config(iT1)

                time.sleep(10)
                soc.reset_gens()

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
            T2R.display(iT2R, dT2R, plotDisp=False, figNum=2)
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
                                             outerFolder=outerFolderT2)
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
                        iT2E = T2EMUX(path="T2E", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolderT2)
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
