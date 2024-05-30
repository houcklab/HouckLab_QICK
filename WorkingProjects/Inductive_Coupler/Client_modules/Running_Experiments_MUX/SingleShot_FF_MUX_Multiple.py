# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *

from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment_Scripts.mT1FF import T1FF
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment_Scripts.mT2R import T2R
from WorkingProjects.Inductive_Coupler.Client_modules.Experiment_Scripts.mChiShift import ChiShift
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mOptimizeReadoutandPulse_FFMUX import ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX



yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

yoko69.SetVoltage(-0.1368)
yoko70.SetVoltage(-0.1542)
yoko71.SetVoltage(-0.2343)
yoko72.SetVoltage(0.1055)

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq

Qubit_Parameters = {
    '12': {'Readout_FF': [25000, 10000, 0, 0], 'Pulse_FF': [18000, 5000, 0, 0],
           'Readout': {'1': {'Frequency': 6963.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5700},
                       '2': {'Frequency': 7033.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000}},
           'Qubit': {'1': {'Frequency': 4940, 'Gain': 1400}, '2': {'Frequency': 4579.8, 'Gain': 1250}}
           },
    # '13': {'Readout_FF': [25000, 0, 17000, 0], 'Pulse_FF': [18000, 0, 7000, 0],
    #        'Readout': {'1': {'Frequency': 6963.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000},
    #                    '3': {'Frequency': 7104.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000}},
    #        'Qubit': {'1': {'Frequency': 4936.8, 'Gain': 1400}, '3': {'Frequency': 4590.4, 'Gain': 2200}}
    #        },
    # '13': {'Readout_FF': [0, 0, 17000, 0], 'Pulse_FF': [18000, 0, 7000, 0],
    '13': {'Readout_FF': [25000, 0, 17000, 0], 'Pulse_FF': [18000, 0, 7000, 0],
        'Readout': {'1': {'Frequency': 6963.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000},
                       '3': {'Frequency': 7104.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000}},
           'Qubit': {'1': {'Frequency': 4936.8, 'Gain': 1400}, '3': {'Frequency': 4590.4 + 1.6, 'Gain': 2800}}
           },
    '14': {'Readout_FF': [18000, 0, 0, -25000], 'Pulse_FF': [5900, 0, 0, -7200],
        'Readout': {'1': {'Frequency': 6962.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000},
                    '4': {'Frequency': 7230.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5500}},
           'Qubit': {'1': {'Frequency': 4590.2, 'Gain': 1620}, '4': {'Frequency': 4616.1, 'Gain': 2900}}
           },

    '23': {'Readout_FF': [0, 13900, 20000, 0], 'Pulse_FF': [0, 8200, 8000, 0],
        'Readout': {'2': {'Frequency': 7033.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000},
                    '3': {'Frequency': 7104.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6200}},
           'Qubit': {'2': {'Frequency': 4670.9, 'Gain': 1600}, '3': {'Frequency': 4615.5, 'Gain': 3050}}
           },
    '24': {'Readout_FF': [0, 9300, 0, -25000], 'Pulse_FF': [0, 5000, 0, -19000],
           'Readout': {'2': {'Frequency': 7033.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6500},
                       '4': {'Frequency': 7230.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000}},
           'Qubit': {'2': {'Frequency': 4582, 'Gain': 1350}, '4': {'Frequency': 4915.4, 'Gain': 2750}}
           },
    '34': {'Readout_FF': [0, 0, 15000, -28000], 'Pulse_FF': [0, 0, 6500, -19000],
           'Readout': {'3': {'Frequency': 7104.6 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000},
                       '4': {'Frequency': 7230.9 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000}},
           'Qubit': {'3': {'Frequency': 4571.1, 'Gain': 2000}, '4': {'Frequency': 4916.5, 'Gain': 2750}}
           }
    }


Qubit_Readout = 34
Qubit_Readout_Specific = [3, 4]
Qubit_Pulse = [4]

# Completed ones:
# 14
# 23
# 13
# 24
# 34


# expt
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout)]['Readout_FF']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Readout)]['Pulse_FF']
gains = [Qubit_Parameters[str(Qubit_Readout)]['Readout'][str(Q_R)]['Gain'] / 32000. * len(Qubit_Readout_Specific) for Q_R in Qubit_Readout_Specific]

BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout_Specific))]


RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain":100, "SpecSpan": 20, "SpecNumPoints": 51, 'Gauss': True, "sigma": 0.05,
                        "gain": 800}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Readout)]['Qubit'][str(Qubit_Pulse[0])]['Frequency'],
                         "sigma": 0.05, "max_gain": 3500}

RunT1 = False
RunT2 = False
T1T2_params = {"T1_step": 4, "T1_expts": 40, "T1_reps": 50, "T1_rounds": 20,
               "T2_step": 0.2, "T2_expts": 100, "T2_reps": 50, "T2_rounds": 20, "freq_shift": 0.5}

SingleShot = True
SS_params = {"Shots": 2000, "Readout_Time": 3, "ADC_Offset": 0.5, "Qubit_Pulse": Qubit_Pulse}

SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 3000, "gain_stop": 9000, "gain_pts": 7, "span": 1.2, "trans_pts": 13}

SingleShot_QubitOptimize = False
SS_Q_params = {"Optimize_Index": 0, "q_gain_span": 500, "q_gain_pts": 11, "q_freq_span": 4, "q_freq_pts": 13}


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}

# cavity_gain = Qubit_Parameters[str(Qubit_Readout)][str(Qubit_Readout_Specific[0])]['Readout']['Gain']
# resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout_Specific[0])]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Readout)]['Qubit'][str(Qubit_Pulse[0])]['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Qubit'][str(Qubit_Pulse[0])]['Frequency']
resonator_frequencies = [Qubit_Parameters[str(Qubit_Readout)]['Readout'][str(Q_R)]['Frequency'] for Q_R in Qubit_Readout_Specific]

gains = [Qubit_Parameters[str(Qubit_Readout)]['Readout'][str(Q_R)]['Gain'] / 32000. * len(Qubit_Readout_Specific) for Q_R in Qubit_Readout_Specific]


print(BaseConfig["mixer_freq"], resonator_frequencies)
# mixer_freq = 7200
# BaseConfig["mixer_freq"] = 7210
# start = -154.2 + 10
# dif = 61.6
# resonator_frequencies = [start, start + dif]
# print(BaseConfig["mixer_freq"], resonator_frequencies)

# FF_Qubits[str(Swept_Qubit)]['Gain_Readout'] = Swept_Qubit_Gain
# FF_Qubits[str(Swept_Qubit)]['Gain_Expt'] = Swept_Qubit_Gain
# FF_Qubits[str(Qubit_Readout)]['Gain_Readout'] = Read_Qubit_Gain
# FF_Qubits[str(Qubit_Readout)]['Gain_Expt'] = Read_Qubit_Gain
# for i in range(4):
#     if i + 1 == Swept_Qubit or i + 1 == Qubit_Readout:
#         continue
#     FF_Qubits[str(i + 1)]['Gain_Readout'] = Bias_Qubit_Gain
#     FF_Qubits[str(i + 1)]['Gain_Expt'] = Bias_Qubit_Gain
#
# print(FF_Qubits)


trans_config = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 3,  # [us]
    # "pulse_gain": cavity_gain,  # [DAC units]
    # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "pulse_gains": gains,  # [DAC units]
    "pulse_freqs": resonator_frequencies,
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
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
config['Read_Indeces'] = Qubit_Readout_Specific

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

cavity_min = True
config["cavity_min"] = cavity_min  # look for dip, not peak
# perform the cavity transmission experiment
if RunTransmissionSweep:
    config["reps"] = 20  # fast axis number of points
    config["rounds"] = 20  # slow axis number of points
    Instance_trans = CavitySpecFFMUX(path="TransmissionFF", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder)
    data_trans = CavitySpecFFMUX.acquire(Instance_trans)
    CavitySpecFFMUX.display(Instance_trans, data_trans, plotDisp=True, figNum=1)
    CavitySpecFFMUX.save_data(Instance_trans, data_trans)
    # update the transmission frequency to be the peak
    if cavity_min:
        config["pulse_freq"] = Instance_trans.peakFreq_min - mixer_freq
    else:
        config["pulse_freq"] = Instance_trans.peakFreq_max - mixer_freq
    print("Cavity frequency found at: ", config["pulse_freq"])
# else:
    # print("Cavity frequency set to: ", config["pulse_freq"])

# qubit spec experiment
if Run2ToneSpec:
    config["reps"] = 30  # want more reps and rounds for qubit data
    config["rounds"] = 30
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
    Instance_specSlice = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFFMUX.acquire(Instance_specSlice)
    QubitSpecSliceFFMUX.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFFMUX.save_data(Instance_specSlice, data_specSlice)

# Amplitude Rabi
number_of_steps = 31
step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 30,
                "sigma": Amplitude_Rabi_params["sigma"], "f_ge": Amplitude_Rabi_params["qubit_freq"],
                "relax_delay": 200}
config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
if RunAmplitudeRabi:
    iAmpRabi = AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFFMUX.acquire(iAmpRabi)
    AmplitudeRabiFFMUX.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFFMUX.save_data(iAmpRabi, dAmpRabi)

#
if RunT1:
    expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                "reps": T1T2_params["T1_reps"],
                "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain, "relax_delay": 200
                }

    config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT1 = T1FF(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT1 = T1FF.acquire(iT1)
    T1FF.display(iT1, dT1, plotDisp=True, figNum=2)
    T1FF.save_data(iT1, dT1)


if RunT2:
    T2R_cfg = {"start": 0, "step": T1T2_params["T1_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
               "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
               "pi_gain": qubit_gain,
               "pi2_gain": qubit_gain // 2, "relax_delay": 200,
               'f_ge': qubit_frequency_center + T1T2_params["freq_shift"]
               }
    config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT2R = T2R(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2R.acquire(iT2R)
    T2R.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2R.save_data(iT2R, dT2R)


qubit_gains = [Qubit_Parameters[str(Qubit_Readout)]['Qubit'][str(Q_R)]['Gain'] for Q_R in SS_params["Qubit_Pulse"]]
qubit_frequency_centers = [Qubit_Parameters[str(Qubit_Readout)]['Qubit'][str(Q_R)]['Frequency'] for Q_R in SS_params["Qubit_Pulse"]]


UpdateConfig = {
    ###### cavity
    # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "read_pulse_style": "const", # --Fixed
    "readout_length": SS_params["Readout_Time"], # us (length of the pulse applied)
    "adc_trig_offset": SS_params["ADC_Offset"],
    # "pulse_gain": cavity_gain, # [DAC units]
    # "pulse_gain": cavity_gain,  # [DAC units]
    # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "pulse_gains": gains,  # [DAC units]
    "pulse_freqs": resonator_frequencies,
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": config["sigma"],  ### units us, define a 20ns sigma
    "qubit_gain": qubit_gain,
    "f_ge": qubit_frequency_center,
    "qubit_gains": qubit_gains,
    "f_ges": qubit_frequency_centers,
    ##### define shots
    "shots": SS_params["Shots"], ### this gets turned into "reps"
    "relax_delay": 200,  # us
}

config = BaseConfig | UpdateConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indeces'] = Qubit_Readout_Specific
print()


print(config)
if SingleShot:
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)


if SingleShot_ReadoutOptimize:
    span = SS_R_params['span']
    cav_gain_start = SS_R_params['gain_start']
    cav_gain_stop = SS_R_params['gain_stop']
    cav_gain_pts = SS_R_params['gain_pts']
    cav_trans_pts = SS_R_params['trans_pts']

    exp_parameters = {
        ###### cavity
        "cav_gain_Start": cav_gain_start,
        "cav_gain_Stop": cav_gain_stop,
        "cav_gain_Points": cav_gain_pts,
        "trans_freq_start": config["mixer_freq"] - span / 2, #249.6,
        "trans_freq_stop": config["mixer_freq"] + span / 2, #250.3,
        "TransNumPoints": cav_trans_pts,
    }
    config = config | exp_parameters
    # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFFMUX.acquire(Instance_SingleShotOptimize, cavityAtten = cavityAtten)
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFFMUX.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    ReadOpt_wSingleShotFFMUX.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFFMUX.save_config(Instance_SingleShotOptimize)

if SingleShot_QubitOptimize:
    q_gain_span = SS_Q_params['q_gain_span']
    q_gain_pts = SS_Q_params['q_gain_pts']
    q_freq_pts = SS_Q_params['q_freq_pts']
    q_freq_span = SS_Q_params['q_freq_span']
    Qubit_Pulse_Index = SS_Q_params['Optimize_Index']
    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": qubit_gains[Qubit_Pulse_Index] - q_gain_span / 2,
        "qubit_gain_Stop": qubit_gains[Qubit_Pulse_Index] + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_centers[Qubit_Pulse_Index] - q_freq_span / 2, #249.6,
        "qubit_freq_stop": qubit_frequency_centers[Qubit_Pulse_Index] + q_freq_span / 2, #250.3,
        "QubitNumPoints": q_freq_pts,
    }
    config = config | exp_parameters
    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFFMUX(path="SingleShot_OptQubit", outerFolder=outerFolder,
                                                                 cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFFMUX.acquire(Instance_SingleShotOptimize,
                                                                            Qubit_Sweep_Index = Qubit_Pulse_Index)
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFFMUX.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    QubitPulseOpt_wSingleShotFFMUX.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFFMUX.save_config(Instance_SingleShotOptimize)