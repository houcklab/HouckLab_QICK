# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Calib.initialize4Q import *
import time
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mTransmissionFF import CavitySpecFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleTone import SingleTone

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSpecSliceFF import QubitSpecSliceFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF import AmplitudeRabiFF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mAmplitudeRabiFF_noUpdate import AmplitudeRabiFF_N
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mChiShift import ChiShift

from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1FF import T1FF
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2R import T2R
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT2EFF import T2EMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mT1_SS import T1_SS
from WorkingProjects.QM_Team.qubit_measurements.Client_modules.Experiments.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF


# from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
# from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift
# from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF import SingleShotProgramFF
# from q4diamond.Client_modules.Experiment_Scripts.mOptimizeReadoutandPulse_FF import ReadOpt_wSingleShotFF, QubitPulseOpt_wSingleShotFF


soc, soccfg = makeProxy()

#### define the saving path

#Readout Qubit Params
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6513.8, 'Gain': int(1000)},
          'Qubit': {'Frequency': 2979.5, 'Gain': int(9000), "sigma": 0.3, "flattop_length": 2.0},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q1_6p5//"},
    '2': {'Readout': {'Frequency': 6631.049, 'Gain': 3200},
          'Qubit': {'Frequency': 3197.64, 'Gain': 6020, "sigma": 0.3, "flattop_length": 2.0}, #0.03 sigma
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q2_6p6//"},
    '3': {'Readout': {'Frequency': 6766.6666, 'Gain': 2000},
          'Qubit': {'Frequency': 3523.887, 'Gain': 5690, "sigma": 0.3, "flattop_length": 2.0},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q3_6p7//"},
    '4': {'Readout': {'Frequency': 6839.835, 'Gain': 1000},
          'Qubit': {'Frequency': 3577.69, 'Gain': 888, "sigma": 0.3, "flattop_length": 0.6},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q4_6p8//"},
    '5': {'Readout': {'Frequency': 7019.173, 'Gain': 1000},
          'Qubit': {'Frequency': 3893.55, 'Gain': 1021, "sigma": 0.3, "flattop_length": 0.6},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q5_7p0//"},
    '6': {'Readout': {'Frequency': 7077.93, 'Gain': 2000},
          'Qubit': {'Frequency': 4025.668, 'Gain': 7300, "sigma": 0.3, "flattop_length": 2},
          'Pulse_FF': [0, 0, 0, 0],
          'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ02-Si_01/Q6_7p1//"},
    }
############# End Can B ############################

############## Start Can C ############################
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6715.6, 'Gain': int(4000)},
#           'Qubit': {'Frequency': 3862.9, 'Gain': int(6500), "sigma": 0.03, "flattop_length": 0.3},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATAl01-Si_01/Q1_6p7//"},
#     '3': {'Readout': {'Frequency': 6922.7, 'Gain': 4000},
#           'Qubit': {'Frequency': 4255.497, 'Gain': 8000, "sigma": 0.2, "flattop_length": 7}, #0.03 sigma
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATAl01-Si_01/Q3_6p9//"},
#     '5': {'Readout': {'Frequency': 7131.8, 'Gain': 4000},
#           'Qubit': {'Frequency': 4558.925, 'Gain': 14000, "sigma": 0.2, "flattop_length": 140},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATAl01-Si_01/Q5_7p1//"},
#     '6': {'Readout': {'Frequency': 7203.9, 'Gain': 3000},
#           'Qubit': {'Frequency': 4964.64, 'Gain': 9500, "sigma": 0.3, "flattop_length": 7},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATAl01-Si_01/Q6_7p2//"},
#     }
############## End Can C ############################

# ############## Start Can D ############################
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6709.94, 'Gain': int(3000)},
#           'Qubit': {'Frequency': 3438.74, 'Gain': int(9000), "sigma": 0.3, "flattop_length": 1.0},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATQ01-Si_03/Q1_6p71//"},
#     '2': {'Readout': {'Frequency': 6818.78, 'Gain': 2300},
#           'Qubit': {'Frequency': 3702, 'Gain': 9000, "sigma": 0.3, "flattop_length": 2.5}, #0.03 sigma
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername':"Z:/t1Team/Data/2024-09-11_cooldown/TATQ01-Si_03/Q2_6p82//"},
#     '3': {'Readout': {'Frequency': 6920.4, 'Gain': 3500 },
#           'Qubit': {'Frequency': 3775, 'Gain': 7400, "sigma": 0.1, "flattop_length": 0.7},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ01-Si_03/Q3_6p92//"},
#     '4': {'Readout': {'Frequency': 7000.8, 'Gain': 1000},
#           'Qubit': {'Frequency': 3949, 'Gain': 6400, "sigma": 0.01, "flattop_length": 0.04},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ01-Si_03/Q4_7p00//"},
#     '5': {'Readout': {'Frequency': 7123.3, 'Gain': 1600},
#           'Qubit': {'Frequency': 4060, 'Gain': 7850, "sigma": 0.03, "flattop_length": 0.3},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ01-Si_03/Q5_7p12//"},
#     '6': {'Readout': {'Frequency': 7206.58, 'Gain': 3000},
#           'Qubit': {'Frequency': 4415, 'Gain': 7300, "sigma": 0.03, "flattop_length": 1.3},
#           'Pulse_FF': [0, 0, 0, 0],
#           'outerfoldername': "Z:/t1Team/Data/2024-09-11_cooldown/TATQ01-Si_03/Q6_7p21//"},
#     }
# ############### End Can D ############################


# Readout
Qubit_Readout = 5
Qubit_Pulse = 5
outerFolder = Qubit_Parameters[str(Qubit_Readout)]['outerfoldername']

ConstantTone = False  # determine cavity frequency

RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain": 3000, "SpecSpan": 0.3, "SpecNumPoints": 101,
                        "reps": 10, 'rounds': 20,
                        'Gauss': True, "sigma": 1, "gain": 10000} # False -- no pulse #If you don't see RabiAmp but with Gauss True see the qubit, the next thing to check is gain, you might not have the right pi pulse

RunChiShift = False
ChiShift_params = {"reps": 1000,
                    'rounds': 1,# this will used for all experiements below unless otherwise changed in between trials
                    "TransSpan": 0.8,  ### MHz, span will be center+/- this parameter
                    "TransNumPoints": 81,
                    "cavity_shift": 0.2,
                    "relax_delay": 4000}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency'],
                         "max_gain": 3000, 'number_of_steps': 31,
                         "reps": 10, 'rounds': 20,
                         'relax_delay': 10000,}  #Always change the max gain if you don't see it, also compare what you get with Transmission data

RunT1 = False
RunT2 = False
T1T2_params = {"T1_step": 50, "T1_expts": 100, "T1_reps": 10, "T1_rounds": 10,
               "T2_step": 2, "T2_expts": 50, "T2_reps": 10, "T2_rounds": 10, "freq_shift": 0.1,
               "relax_delay": 5000,
               'repetitions': 1}
# T1T2_params = {"T1_step": 50, "T1_expts": 30, "T1_reps": 10, "T1_rounds": 10,
#                "T2_step": 1.7, "T2_expts": 100, "T2_reps": 20, "T2_rounds": 20, "freq_shift": 0.25,
#                "relax_delay": 2000}
RunT2E = False
T2E_params = {"T2_max_us": 200, "T2_expts": 400, "T2_reps": 1, "T2_rounds": 200, "freq_shift": 0.08,
               "relax_delay": 4000, 'num_pi_pulses': 0, #need odd number of pulses
               "pi2_gain": 2580,
              "rotation_angle": 0.31478884,
              "min_max": [7.066475706582131, 0.4586852251182118]}

SingleShot = True
SS_params = {"Shots": 1000, "Readout_Time": 5, "ADC_Offset": 0.5, "Qubit_Pulse": [Qubit_Pulse],
             'number_of_pulses': 1, 'relax_delay': 5000}

RunT1SS = False
T1SS_params = {"T1_step": 75, "T1_expts": 40,
               "reps": 1000,
               'angle': 0.38920197938248996, 'threshold': 1.6117224595654793,
               "relax_delay": 5000,
               'calibrate_SS': True,
               'repetitions': 120}

SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 200, "gain_stop": 7000, "gain_pts": 9, "span": 0.6, "trans_pts": 7}

SingleShot_QubitOptimize = False
#gain_span is now in percent
SS_Q_params = {"q_gain_span": 0.5, "q_gain_pts": 11, "q_freq_span": 0.5, "q_freq_pts": 11,
               'number_of_pulses': 1} # for optimizing pi/2 pulse, set the gain to the half of its value and optimize for n=2


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
qubit_config = {
    "qubit_pulse_style": "const",
    "qubit_gain": Spec_relevant_params["qubit_gain"],
    "qubit_freq": qubit_frequency_center,
    "qubit_length": 100,
    "SpecSpan": Spec_relevant_params["SpecSpan"],  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": Spec_relevant_params["SpecNumPoints"],  ### number of points in the transmission frequecny
}
expt_cfg = {
    "step": 2 * qubit_config["SpecSpan"] / qubit_config["SpecNumPoints"],
    "start": qubit_config["qubit_freq"] - qubit_config["SpecSpan"],
    "expts": qubit_config["SpecNumPoints"]
}

UpdateConfig = trans_config | qubit_config | expt_cfg
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

if ConstantTone:
    Instance_trans = SingleTone(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = SingleTone.acquire(Instance_trans)

cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak
# perform the cavity transmission experiment
if RunTransmissionSweep:
    config["reps"] = 20  # fast axis number of points
    config["rounds"] = 20  # slow axis number of points
    Instance_trans = CavitySpecFF(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = CavitySpecFF.acquire(Instance_trans)
    CavitySpecFF.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFF.save_data(Instance_trans, data_trans)
    CavitySpecFF.save_config(Instance_trans)

    # update the transmission frequency to be the peak
    if cavity_min:
        config["pulse_freq"] = Instance_trans.peakFreq_min
    else:
        config["pulse_freq"] = Instance_trans.peakFreq_max
    print("Cavity frequency found at: ", config["pulse_freq"])
else:
    print("Cavity frequency set to: ", config["pulse_freq"])



# qubit spec experiment
if Run2ToneSpec:
    config["reps"] = Spec_relevant_params['reps']  # want more reps and rounds for qubit data
    config["rounds"] = Spec_relevant_params['rounds']
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
    Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)
    QubitSpecSliceFF.save_config(Instance_specSlice)

if RunChiShift:
    updated_params = {
        "pi_gain": qubit_gain,
        "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
        "flattop_length": qubit_flattop
    }
    config = config | ChiShift_params | updated_params
    iChi = ChiShift(path="ChiShift", cfg=config, soc=soc, soccfg=soccfg,
                    outerFolder=outerFolder)
    dChi = ChiShift.acquire(iChi)
    ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
    ChiShift.save_data(iChi, dChi)
    ChiShift.save_config(iChi)

# Amplitude Rabi
  ### note that UpdateConfig will overwrite elements in BaseConfig

if RunAmplitudeRabi:
    number_of_steps = Amplitude_Rabi_params["number_of_steps"]
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": Amplitude_Rabi_params['reps'],
                    "rounds": Amplitude_Rabi_params['rounds'],
                    "sigma": qubit_sigma, "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": Amplitude_Rabi_params["relax_delay"],
                    "flattop_length": qubit_flattop}

    config = config | ARabi_config
    if qubit_flattop != None:
        ARabi_config = {'gain_start': 0, "gain_end": Amplitude_Rabi_params["max_gain"],
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
        AmplitudeRabiFF_N.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
        AmplitudeRabiFF_N.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF_N.save_config(iAmpRabi)
    else:
        iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                                   outerFolder=outerFolder)
        dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
        AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
        AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)
        AmplitudeRabiFF.save_config(iAmpRabi)

#
if RunT1:
    for i in range(T1T2_params['repetitions']):
        if T1T2_params['repetitions'] > 1:
            plot_disp = False
        else:
            plot_disp = True
        expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                    "reps": T1T2_params["T1_reps"],"Qubit_number": Qubit_Readout,
                    "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain, "relax_delay": T1T2_params["relax_delay"],
                    "sigma": qubit_sigma, "flattop_length": qubit_flattop,
                    "f_ge": qubit_frequency_center
                    }

        config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT1 = T1FF(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT1 = T1FF.acquire(iT1)
        T1FF.display(iT1, dT1, plotDisp=plot_disp, figNum=2)
        T1FF.save_data(iT1, dT1)
        T1FF.save_config(iT1)

        time.sleep(10)
        soc.reset_gens()


if RunT2:
    T2R_cfg = {"start": 0, "step": T1T2_params["T2_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
               "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
               "pi_gain": qubit_gain,
               "pi2_gain": qubit_gain // 2, "relax_delay": T1T2_params["relax_delay"],
               'f_ge': qubit_frequency_center + T1T2_params["freq_shift"],
               "sigma": qubit_sigma, "flattop_length": qubit_flattop
               }
    config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2R.acquire(iT2R)
    T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2R.save_data(iT2R, dT2R)
    T2R.save_config(iT2R)


if RunT2E:
    if T2E_params["pi2_gain"] == False:
        qubit_gain_pi2 = qubit_gain // 2
    else:
        qubit_gain_pi2 = T2E_params["pi2_gain"]
    num_pulses = T2E_params["num_pi_pulses"]
    int_steps = T2E_params["T2_max_us"] // (0.00232515 * (num_pulses + 1) * T2E_params["T2_expts"])
    print(int_steps, 0.00232515 * (num_pulses + 1) * int_steps, T2E_params["T2_expts"])
    T2E_cfg = {"start": 0, "step": 0.00232515 * (num_pulses + 1) * int_steps,
               "expts": T2E_params["T2_expts"], "reps": T2E_params["T2_reps"], "rounds": T2E_params["T2_rounds"],
               "pi_gain": qubit_gain,
               "pi2_gain": qubit_gain_pi2, "relax_delay": T2E_params["relax_delay"],
               'f_ge': qubit_frequency_center + T2E_params["freq_shift"],
               "num_pi_pulses": T2E_params["num_pi_pulses"],
               "sigma": qubit_sigma, "flattop_length": qubit_flattop
               }
    if T2E_params["rotation_angle"] != False:
        T2E_cfg["rotation_angle"] = T2E_params["rotation_angle"]
        T2E_cfg["min_max"] = T2E_params["min_max"]

    if int_steps == 0:
        print('Step size is 0! need to increase total time or decrease experiments')
    else:
        config = config | T2E_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT2E = T2EMUX(path="T2E", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT2E = T2EMUX.acquire(iT2E)
        T2EMUX.display(iT2E, dT2E, plotDisp=True, figNum=2)
        T2EMUX.save_data(iT2E, dT2E)
        T2EMUX.save_config(iT2E)




#######################################################
qubit_gains = [Qubit_Parameters[str(Q_R)]['Qubit']['Gain'] for Q_R in SS_params["Qubit_Pulse"]]
qubit_frequency_centers = [Qubit_Parameters[str(Q_R)]['Qubit']['Frequency'] for Q_R in SS_params["Qubit_Pulse"]]


UpdateConfig = {
    ###### cavity
    # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "read_pulse_style": "const", # --Fixed
    "readout_length": SS_params["Readout_Time"], # us (length of the pulse applied)
    "adc_trig_offset": SS_params["ADC_Offset"],
    # "pulse_gain": cavity_gain, # [DAC units]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": qubit_sigma,  ### units us, define a 20ns sigma
    "qubit_gain": qubit_gain,
    "f_ge": qubit_frequency_center,
    "qubit_gains": qubit_gains,
    "f_ges": qubit_frequency_centers,
    ##### define shots
    "shots": SS_params["Shots"], ### this gets turned into "reps"
    "relax_delay": SS_params['relax_delay'],  # us
    "flattop_length": qubit_flattop
}

config = BaseConfig | UpdateConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indeces'] = Qubit_Readout


if SingleShot:
    config['number_of_pulses'] = SS_params['number_of_pulses']
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
    print('Angle: ', data_SingleShotProgram['data']['angle'][0])
    print('threshold: ', data_SingleShotProgram['data']['threshold'][0])

if RunT1SS:
    for i in range(T1SS_params["repetitions"]):
        if T1SS_params["calibrate_SS"]:
            config['number_of_pulses'] = SS_params['number_of_pulses']
            Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                                soc=soc, soccfg=soccfg)
            data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
            SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=False)
            SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
            SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)
            angle = data_SingleShotProgram['data']['angle'][0]
            threshold = data_SingleShotProgram['data']['threshold'][0]
        else:
            angle = T1SS_params["angle"]
            threshold = T1SS_params["threshold"]
        print(angle, threshold)

        expt_cfg = {"start": 0, "step": T1SS_params["T1_step"], "expts": T1SS_params["T1_expts"],
                    'reps': T1SS_params['reps'],
                    "pi_gain": qubit_gain, "relax_delay": T1SS_params["relax_delay"]
                    }
        config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
        iT1 = T1_SS(path="T1SS", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
        dT1 = T1_SS.acquire(iT1, angle = angle, threshold = threshold)
        T1_SS.display(iT1, dT1, plotDisp=False, figNum=2)
        T1_SS.save_data(iT1, dT1)
        T1_SS.save_config(iT1)

        time.sleep(10)
        soc.reset_gens()


if SingleShot_ReadoutOptimize:
    span = SS_R_params['span']
    cav_gain_start = SS_R_params['gain_start']
    cav_gain_stop = SS_R_params['gain_stop']
    cav_gain_pts = SS_R_params['gain_pts']
    cav_trans_pts = SS_R_params['trans_pts']
    config['number_of_pulses'] = 1
    exp_parameters = {
        ###### cavity
        "cav_gain_Start": cav_gain_start,
        "cav_gain_Stop": cav_gain_stop,
        "cav_gain_Points": cav_gain_pts,
        "trans_freq_start": config["pulse_freq"] - span / 2, #249.6,
        "trans_freq_stop": config["pulse_freq"] + span / 2, #250.3,
        "TransNumPoints": cav_trans_pts,
    }
    config = config | exp_parameters
    # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFF(path="SingleShot_OptReadout", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize)
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    ReadOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)




if SingleShot_QubitOptimize:
    q_gain_span = SS_Q_params['q_gain_span']
    q_gain_pts = SS_Q_params['q_gain_pts']
    q_freq_pts = SS_Q_params['q_freq_pts']
    q_freq_span = SS_Q_params['q_freq_span']
    config['number_of_pulses'] = SS_Q_params['number_of_pulses']
    Qubit_Pulse_Index = 0
    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": max([0, int(qubit_gains[Qubit_Pulse_Index] * (1 - q_gain_span))]), # - q_gain_span / 2,
        "qubit_gain_Stop":  min([32767, int(qubit_gains[Qubit_Pulse_Index] * (1 + q_gain_span))]),# *qubit_gains[Qubit_Pulse_Index] + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_centers[Qubit_Pulse_Index] - q_freq_span / 2, #249.6,
        "qubit_freq_stop": qubit_frequency_centers[Qubit_Pulse_Index] + q_freq_span / 2, #250.3,
        "QubitNumPoints": q_freq_pts,
        "number_of_pulses": SS_Q_params["number_of_pulses"]
    }
    config = config | exp_parameters
    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFF(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                                                 cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize,
                                                                            Qubit_Sweep_Index = Qubit_Pulse_Index)
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    QubitPulseOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)
###############################################