# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from WorkingProjects.Inductive_Coupler.Client_modules.Running_Experiments_MUX.MUXInitialize import *

from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSpecSliceFFMUX_CW import QubitSpecSliceFFMUXCW
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mChiShiftMUX import ChiShift
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mOptimizeReadoutandPulse_FFMUX import ReadOpt_wSingleShotFFMUX, QubitPulseOpt_wSingleShotFFMUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mT1MUX import T1MUX
from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mT2RMUX import T2RMUX

from WorkingProjects.Inductive_Coupler.Client_modules.Experimental_Scripts_MUX.mT2R_TwoPulses import T2R_2PulseMUX, T2R_2PulseMUX_NoUpdate

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6999.25 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5500,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 5380, 'Gain': 2500},
          'Pulse_FF': [0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7091.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8000,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 1.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 5430, 'Gain': 760},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7192.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 8800,
                      "FF_Gains": [0, 0, 0, 0], "Readout_Time": 1.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit': {'Frequency': 5546, 'Gain': 2424},
          'Pulse_FF': [0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7283.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 11000,
                    "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
          'Qubit': {'Frequency': 5580, 'Gain': 1626},
          'Pulse_FF': [0, 0, 0, 0]}
    }

# expt
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

Qubit_Readout = [1]
Qubit_Pulse = [1]

FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse[0])]['Pulse_FF']

# Qubit_Read_Gain = 0
# Qubit_Sweep = 4
# Qubit_Sweep_Gain = 13000
# FF_Gains = [-30000, -30000, -30000, -30000]
# # FF_Gains = [0, 0, 0, 0]
# FF_Gains[Qubit_Readout[0] - 1] = Qubit_Read_Gain
# FF_Gains[Qubit_Sweep - 1] = Qubit_Sweep_Gain
# FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = FF_Gains
# FF_Gains[Qubit_Readout[0] - 1] = 0
# FF_gain1, FF_gain2, FF_gain3, FF_gain4 = FF_Gains


gains = [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout]

BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout))]


RunTransmissionSweep = True  # determine cavity frequency
Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain": 500, "SpecSpan": 50, "SpecNumPoints": 51, 'Gauss': False, "sigma": 0.05,
                        "gain": 5500}
# Spec_relevant_params = {"qubit_gain": 500, "SpecSpan": 150, "SpecNumPoints": 101, 'Gauss': True, "sigma": 0.05,
#                         "gain": 1230}
# Spec_relevant_params = {"qubit_gain": 120, "SpecSpan": 10, "SpecNumPoints": 51, 'Gauss': False, "sigma": 0.05,
#                         "gain": 600}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'],
                         "sigma": 0.03, "max_gain": 4000}

RunT1 = False
RunT2 = False
# T1T2_params = {"T1_step": 5, "T1_expts": 60, "T1_reps": 50, "T1_rounds": 20,
#                "T2_step": 0.015, "T2_expts": 30*4 * 4, "T2_reps": 100, "T2_rounds": 100, "freq_shift": 2.5,
#                "relax_delay": 500}
T1T2_params = {"T1_step": 0.7, "T1_expts": 100, "T1_reps": 50, "T1_rounds": 50,
               "T2_step":0.25, "T2_expts": 200, "T2_reps": 50, "T2_rounds": 50, "freq_shift": 0,
               "relax_delay": 500}

# T1T2_params = {"T1_step": 0.6, "T1_expts": 90, "T1_reps": 40, "T1_rounds": 40,
#                "T2_step": 0.8, "T2_expts": 1000, "T2_reps": 50, "T2_rounds": 40, "freq_shift": 0.5,
#                "relax_delay": 130}

SingleShot = False
SS_params = {"Shots": 2000, "Readout_Time": 2, "ADC_Offset": 0.3, "Qubit_Pulse": Qubit_Pulse}
# SS_params = {"Shots": 100000, "Readout_Time": 35, "ADC_Offset": 0.5, "Qubit_Pulse": Qubit_Pulse}

SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 7000, "gain_stop": 12000, "gain_pts": 11, "span": 1.2, "trans_pts": 7}
# SS_R_params = {"gain_start": 4000, "gain_stop": 6000, "gain_pts": 7, "span": 1, "trans_pts": 7}

SingleShot_QubitOptimize = False
SS_Q_params = {"Optimize_Index": 0, "q_gain_span": 1000, "q_gain_pts": 6, "q_freq_span": 3, "q_freq_pts": 11}

RunChiShift = False
ChiShift_Params = {'pulse_expt': {'check_12': False},
                   'qubit_freq01': Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'], 'qubit_gain01': 1670 // 2,
                   'qubit_freq12':  Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency'],  'qubit_gain12': 1670 // 2}


Run2ToneSpecCW = False
Spec_relevant_paramsCW = {"qubit_gain": 150, "SpecSpan": 60, "SpecNumPoints": 51, 'Gauss': False, "sigma": 0.05,
                        "gain": 1230}

FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}


cavity_gain = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit']['Frequency']
resonator_frequencies = [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout]


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
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
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
config['Read_Indeces'] = Qubit_Readout


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
    print('freqs before: ', config["pulse_freqs"])

    if Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['cavmin']:
        config["pulse_freqs"][0] += Instance_trans.peakFreq_min - mixer_freq
        config["mixer_freq"] = Instance_trans.peakFreq_min
    else:
        config["pulse_freqs"][0] += Instance_trans.peakFreq_max - mixer_freq + 0.3
        config["mixer_freq"] = Instance_trans.peakFreq_max

    print('min freq; ', Instance_trans.peakFreq_min)
    print('freqs after: ', config["pulse_freqs"])
    print("Cavity frequency found at: ", config["pulse_freqs"][0] + mixer_freq + BaseConfig["cavity_LO"] / 1e6)
else:
    print("Cavity frequency set to: ", config["pulse_freqs"][0] + mixer_freq + BaseConfig["cavity_LO"] / 1e6)

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

if Run2ToneSpecCW:
    config["reps"] = 30  # want more reps and rounds for qubit data
    config["rounds"] = 30
    Instance_specSlice = QubitSpecSliceFFMUXCW(path="QubitSpecFFCW", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFFMUXCW.acquire(Instance_specSlice)
    QubitSpecSliceFFMUXCW.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFFMUXCW.save_data(Instance_specSlice, data_specSlice)

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
                "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain, "relax_delay": T1T2_params["relax_delay"]
                }

    config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT1 = T1MUX(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT1 = T1MUX.acquire(iT1)
    T1MUX.display(iT1, dT1, plotDisp=True, figNum=2)
    T1MUX.save_data(iT1, dT1)


if RunT2:
    T2R_cfg = {"start": 0, "step": T1T2_params["T2_step"], "phase_step": soccfg.deg2reg(0 * 360 / 50, gen_ch=2),
               "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
               "pi_gain": qubit_gain,
               "pi2_gain": qubit_gain // 2, "relax_delay": T1T2_params["relax_delay"],
               'f_ge': qubit_frequency_center + T1T2_params["freq_shift"]
               }
    config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT2R = T2RMUX(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2RMUX.acquire(iT2R)
    T2RMUX.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2RMUX.save_data(iT2R, dT2R)

if RunChiShift:
    config = config | ChiShift_Params
    iChi = ChiShift(path="ChiShift", cfg=config,soc=soc,soccfg=soccfg,
                                      outerFolder=outerFolder)
    dChi = ChiShift.acquire(iChi)
    ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
    ChiShift.save_data(iChi, dChi)

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
    "relax_delay": 1000,  # us
}

config = BaseConfig | UpdateConfig
config["FF_Qubits"] = FF_Qubits
config['Read_Indeces'] = Qubit_Readout


print(config)
if SingleShot:
    print(config)
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
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFFMUX.acquire(Instance_SingleShotOptimize)
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




#
# all_gains = [22000, 20000, 17000, 15000, 12000, 9000, 6000, 3000, 0.01]
# all_gains = [10000, 11000]
#
# # all_gains = [ -5000, -10000, -20000]
# for g in all_gains:
#     qubit_gains = [Qubit_Parameters[str(Q_R)]['Qubit']['Gain'] for Q_R in SS_params["Qubit_Pulse"]]
#     qubit_frequency_centers = [Qubit_Parameters[str(Q_R)]['Qubit']['Frequency'] for Q_R in SS_params["Qubit_Pulse"]]
#
#     UpdateConfig = {
#         ###### cavity
#         # "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
#         "read_pulse_style": "const",  # --Fixed
#         "readout_length": SS_params["Readout_Time"],  # us (length of the pulse applied)
#         "adc_trig_offset": SS_params["ADC_Offset"],
#         # "pulse_gain": cavity_gain, # [DAC units]
#         "pulse_gain": cavity_gain,  # [DAC units]
#         "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
#         "pulse_gains": gains,  # [DAC units]
#         "pulse_freqs": resonator_frequencies,
#         ##### qubit spec parameters
#         "qubit_pulse_style": "arb",
#         "sigma": config["sigma"],  ### units us, define a 20ns sigma
#         "qubit_gain": qubit_gain,
#         "f_ge": qubit_frequency_center,
#         "qubit_gains": qubit_gains,
#         "f_ges": qubit_frequency_centers,
#         ##### define shots
#         "shots": SS_params["Shots"],  ### this gets turned into "reps"
#         "relax_delay": 200,  # us
#     }
#
#     config = BaseConfig | UpdateConfig
#     config["FF_Qubits"] = FF_Qubits
#     config['Read_Indeces'] = Qubit_Readout
#
#
#     config["FF_Qubits"][str(4)]['Gain_Readout'] = g
#     # print(config["FF_Qubits"])
#     if SingleShot_ReadoutOptimize:
#         print('gain', g)
#         soc.reset_gens()
#         span = SS_R_params['span']
#         cav_gain_start = SS_R_params['gain_start']
#         cav_gain_stop = SS_R_params['gain_stop']
#         cav_gain_pts = SS_R_params['gain_pts']
#         cav_trans_pts = SS_R_params['trans_pts']
#
#         exp_parameters = {
#             ###### cavity
#             "cav_gain_Start": cav_gain_start,
#             "cav_gain_Stop": cav_gain_stop,
#             "cav_gain_Points": cav_gain_pts,
#             "trans_freq_start": config["mixer_freq"] - span / 2, #249.6,
#             "trans_freq_stop": config["mixer_freq"] + span / 2, #250.3,
#             "TransNumPoints": cav_trans_pts,
#         }
#         config = config | exp_parameters
#         # Now lets optimize powers and readout frequencies
#         Instance_SingleShotOptimize = ReadOpt_wSingleShotFFMUX(path="SingleShot_OptReadout", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
#         data_SingleShotProgramOptimize = ReadOpt_wSingleShotFFMUX.acquire(Instance_SingleShotOptimize, cavityAtten = cavityAtten)
#         # print(data_SingleShotProgram)
#         ReadOpt_wSingleShotFFMUX.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)
#
#         ReadOpt_wSingleShotFFMUX.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
#         ReadOpt_wSingleShotFFMUX.save_config(Instance_SingleShotOptimize)
#         print('gain',g)