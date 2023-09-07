# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *

from q4diamond.Client_modules.Experiment_Scripts.mTransmissionFF import CavitySpecFF
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF import QubitSpecSliceFF
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
from q4diamond.Client_modules.Experiment_Scripts.mT1FF import T1FF
from q4diamond.Client_modules.Experiment_Scripts.mT2R import T2R
from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift
from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF import SingleShotProgramFF
from q4diamond.Client_modules.Experiment_Scripts.mOptimizeReadoutandPulse_FF import *
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF_HigherLevels import AmplitudeRabiFF_HigherExc
from q4diamond.Client_modules.Experiment_Scripts.mSpecSliceFF_HigherLevels import SpecSliceFF_HigherExc
from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF_HigherLevels import SingleShotProgramFF_2States, SingleShotProgramFF_HigherLevels


#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_R\\"

yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

# yoko69.SetVoltage(-0.1656)
# yoko70.SetVoltage(-0.1978)
# yoko71.SetVoltage(-0.0586)
# yoko72.SetVoltage(-0.0564)

# yoko69.SetVoltage(-0.0999)
# yoko70.SetVoltage(-0.2528)
# yoko71.SetVoltage(-0.3299)
# yoko72.SetVoltage(0.2747)

# yoko69.SetVoltage(-0.0928)
# yoko70.SetVoltage(-0.2451)
# yoko71.SetVoltage(-0.315)
# yoko72.SetVoltage(0.2793)
#
# #Readout Qubit Params
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.5, 'Gain': 9500, "FF_Gains": [-11000, 0, 0, 0]},
#           'Qubit01': {'Frequency': 4664.1, 'Gain': 1380},
#           'Qubit12': {'Frequency': 4510.7, 'Gain': 640},
#           'Pulse_FF': [-11000, 0, 0, 0]},
#     # '1': {'Readout': {'Frequency': 6952.3, 'Gain': 7000, "FF_Gains": [-11000, 0, 0, 0]},
#     #       'Qubit01': {'Frequency': 4664.1, 'Gain': 1380},
#     #       'Qubit12': {'Frequency': 4510.7, 'Gain': 640},
#     #       'Pulse_FF': [-11000, 0, 0, 0]},
#     '2': {'Readout': {'Frequency': 7055.6, 'Gain': 8000, "FF_Gains": [0, 11000, 0, 0]},
#           'Qubit01': {'Frequency': 4693, 'Gain': 1000},
#           'Qubit12': {'Frequency': 4538.2 , 'Gain': 790},
#           'Pulse_FF': [0, 11000, 0, 0]},
#     '3': {'Readout': {'Frequency': 7117.1, 'Gain': 8000, "FF_Gains": [0, 0, 11000, 0]},
#           'Qubit01': {'Frequency': 4692.7, 'Gain': 1330},
#           'Qubit12': {'Frequency': 4538.4, 'Gain': 680},
#           'Pulse_FF': [0, 0, 11000, 0]},
#     '4': {'Readout': {'Frequency': 7249.6, 'Gain': 7500, "FF_Gains": [0, 0, 0, -14000]},
#           'Qubit01': {'Frequency': 4670.5, 'Gain': 1500},
#           'Qubit12': {'Frequency': 4516.3, 'Gain': 820},
#           'Pulse_FF': [0, 0, 0, -14000] }
#     }

# yoko69.SetVoltage(-0.0938)
# yoko70.SetVoltage(-0.2283)
# yoko71.SetVoltage(-0.0411)
# yoko72.SetVoltage(0.2724)
#
# #Readout Qubit Params
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.7, 'Gain': 11500, "FF_Gains": [0, -15000, 0, -14000]},
#           'Qubit01': {'Frequency':  4703.7 - 0.6, 'Gain': 870},
#           'Qubit12': {'Frequency': 4547.8 + 0.6, 'Gain': 780},
#           'Pulse_FF': [0, -8000, 0, -15000]},
#     '2': {'Readout': {'Frequency': 7055.3, 'Gain': 11000, "FF_Gains": [-11000, 0, 0, -14000]},
#           'Qubit01': {'Frequency': 4431.3, 'Gain': 1000},
#           'Qubit12': {'Frequency': 4274.2, 'Gain': 1800},
#           'Pulse_FF': [-11000, 0, 0, -14000]},
#     '3': {'Readout': {'Frequency': 7117.05, 'Gain': 6000}, 'Qubit01': {'Frequency': 4420.16, 'Gain': 2100},
#           'Qubit12': {'Frequency': 4230.67, 'Gain': 1160},
#           'Pulse_FF': [-12700, 18000, 0, -14000]},
#     '4': {'Readout': {'Frequency': 7249.6, 'Gain': 7500}, 'Qubit01': {'Frequency': 4670.6, 'Gain': 1550},
#           'Qubit12': {'Frequency': 4516.3 - 0, 'Gain': 970 - 200},
#           'Pulse_FF': [0, 0, 0, -14000]}
#     }

# yoko69.SetVoltage(-0.0622)
# yoko70.SetVoltage(-0.2662)
# yoko71.SetVoltage(-0.3391)
# yoko72.SetVoltage(0.328)

# yoko69.SetVoltage(-0.1214)
# yoko70.SetVoltage(-0.2226)
# yoko71.SetVoltage(-0.2905)
# yoko72.SetVoltage(0.2407)

#Readout Qubit Params
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6953, 'Gain': 9500, "FF_Gains": [-15900, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
          'Qubit01': {'Frequency':  4683.5, 'Gain': 1180},
          'Qubit12': {'Frequency': 4531.2, 'Gain': 770},
          'Pulse_FF': [-9800, 0, 0, 0]},
    # '2': {'Readout': {'Frequency': 7055.8, 'Gain': 7000, "FF_Gains": [0, 10000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
    #       'Qubit01': {'Frequency': 4646.6, 'Gain': 1850},
    #       'Qubit12': {'Frequency': 4497.8, 'Gain': 880},
    #       'Pulse_FF': [0, 7800, 0, 0]},
    '2': {'Readout': {'Frequency': 7055.6, 'Gain': 7500, "FF_Gains": [0, 10000, 0, 0], "Readout_Time": 2.5,
                      "ADC_Offset": 0.3},
          'Qubit01': {'Frequency': 4680.9, 'Gain': 1200},
          'Qubit12': {'Frequency': 4528.3, 'Gain': 830},
          'Pulse_FF': [0, 9000, 0, 0]},
    # '2': {'Readout': {'Frequency': 7055.8, 'Gain': 7000, "FF_Gains": [0, 17000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
    #       'Qubit01': {'Frequency': 4648.5, 'Gain': 1800},
    #       'Qubit12': {'Frequency': 4494.4, 'Gain': 750 * 0},
    #       'Pulse_FF': [0, 11000, 0, 0]},
    '3': {'Readout': {'Frequency': 7117.2, 'Gain': 9000, "FF_Gains": [0, 0, 11000, 0]},
          'Qubit01': {'Frequency': 4654.4, 'Gain': 1770},
          'Qubit12': {'Frequency': 4504.8, 'Gain': 1000},
          'Pulse_FF': [0, 0, 8000, 0]},
    '4': {'Readout': {'Frequency': 7249.7, 'Gain': 8000, "FF_Gains": [0, 0, 0, -17000]},
          'Qubit01': {'Frequency': 4686.1, 'Gain': 1170},
          'Qubit12': {'Frequency': 4532.5, 'Gain': 700},
          'Pulse_FF': [0, 0, 0, -12000]}
    }

#12 optimized readout freq Qubit Params
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6952.45, 'Gain': 7000, "FF_Gains": [-13000, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
          'Qubit01': {'Frequency':  4703.4, 'Gain': 890},
          'Qubit12': {'Frequency': 4550.0, 'Gain': 950},
          'Pulse_FF': [-10500, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7055.3, 'Gain': 6500, "FF_Gains": [0, 10000, 0, 0], "Readout_Time": 2.5,
                      "ADC_Offset": 0.3},
          'Qubit01': {'Frequency': 4680.9, 'Gain': 1200},
          'Qubit12': {'Frequency': 4528.3, 'Gain': 830},
          'Pulse_FF': [0, 9000, 0, 0]},
    '3': {'Readout': {'Frequency': 7116.9, 'Gain': 8000, "FF_Gains": [0, 0, 13600, 0]},
          'Qubit01': {'Frequency': 4698.9, 'Gain': 1280},
          'Qubit12': {'Frequency': 4545.8, 'Gain': 720},
          'Pulse_FF': [0, 0, 9500, 0]},
    '4': {'Readout': {'Frequency': 7249.5, 'Gain': 8000, "FF_Gains": [0, 0, 0, -15000]},
          'Qubit01': {'Frequency': 4686.1, 'Gain': 1170},
          'Qubit12': {'Frequency': 4532.8, 'Gain': 680},
          'Pulse_FF': [0, 0, 0, -12000]}
    }
#NEw frequency params by adding FFdirect before pi pulse
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.45, 'Gain': 7000, "FF_Gains": [-13000, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
#           'Qubit01': {'Frequency':  4684.4, 'Gain': 1130},
#           'Qubit12': {'Frequency': 4531.9, 'Gain': 760},
#           'Pulse_FF': [-9800, 0, 0, 0]},
#     '2': {'Readout': {'Frequency': 7055.3, 'Gain': 6500, "FF_Gains": [0, 10000, 0, 0], "Readout_Time": 2.5,
#                       "ADC_Offset": 0.3},
#           'Qubit01': {'Frequency': 4680.9, 'Gain': 1200},
#           'Qubit12': {'Frequency': 4528.3, 'Gain': 830},
#           'Pulse_FF': [0, 9000, 0, 0]},
#     '3': {'Readout': {'Frequency': 7116.9, 'Gain': 8000, "FF_Gains": [0, 0, 13600, 0]},
#           'Qubit01': {'Frequency': 4698.9, 'Gain': 1280},
#           'Qubit12': {'Frequency': 4545.8, 'Gain': 720},
#           'Pulse_FF': [0, 0, 9500, 0]},
#     '4': {'Readout': {'Frequency': 7249.5, 'Gain': 8000, "FF_Gains": [0, 0, 0, -15000]},
#           'Qubit01': {'Frequency': 4686.1, 'Gain': 1170},
#           'Qubit12': {'Frequency': 4532.8, 'Gain': 680},
#           'Pulse_FF': [0, 0, 0, -12000]}
#     }



# #Qubit 1:
# yoko69.SetVoltage(-0.126)
# yoko70.SetVoltage(0.0171)
# yoko71.SetVoltage(-0.0514)
# yoko72.SetVoltage(-0.0493)

# #Qubit 2:
# yoko69.SetVoltage(-0.2748)
# yoko70.SetVoltage(-0.2268)
# yoko71.SetVoltage(-0.0448)
# yoko72.SetVoltage(-0.055)

# #Qubit 3
# yoko69.SetVoltage(0.2968)
# yoko70.SetVoltage(0.0216)
# yoko71.SetVoltage(-0.2999)
# yoko72.SetVoltage(-0.0421)

#Qubit 4:
yoko69.SetVoltage(-0.2756)
yoko70.SetVoltage(0.0217)
yoko71.SetVoltage(-0.0499)
yoko72.SetVoltage(0.2457)

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6952.51, 'Gain': 10000, "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
          'Qubit01': {'Frequency': 4450.4, 'Gain': 400}, #880},
          'Qubit12': {'Frequency': 4293.0, 'Gain': 930},
          'Pulse_FF': [0, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7055.8, 'Gain': 6000, "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5,
                      "ADC_Offset": 0.3},
          'Qubit01': {'Frequency': 4449.85, 'Gain': 400},
          'Qubit12': {'Frequency': 4292.3, 'Gain': 860},
          'Pulse_FF': [0, 0, 0, 0]},
    '3': {'Readout': {'Frequency': 7117.05, 'Gain': 6000, "FF_Gains": [0, 0, 0, 0]},
          'Qubit01': {'Frequency': 4449.2, 'Gain': 750},
          'Qubit12': {'Frequency': 4290.1, 'Gain': 830},
          'Pulse_FF': [0, 0, 0, 0]},
    '4': {'Readout': {'Frequency': 7249.77, 'Gain': 6000, "FF_Gains": [0, 0, 0, 0]},
          'Qubit01': {'Frequency': 4448.7, 'Gain': 560},
          'Qubit12': {'Frequency': 4290.75, 'Gain': 800},
          'Pulse_FF': [0, 0, 0, 0]}
    }

Qubit_Readout = 4
Qubit_Pulse = 4

# expt
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout)]['Readout']["FF_Gains"]

RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False
Spec_relevant_params = {"qubit_gain":50, "SpecSpan": 5, "SpecNumPoints": 61, 'Gauss': False, "sigma": 0.05,
                        "gain": 2170}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency'],
                         "sigma": 0.1, "max_gain": 1000}

Run2ToneSpec_2nd = False
Spec_relevant_params_Higher = {"qubit_gain": 40, "SpecSpan": 6, "SpecNumPoints": 61, 'Gauss': False, "sigma": 0.1,
                    "gain": 1670}

RunAmplitudeRabi_2nd = True
Amplitude_Rabi_params_2nd = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency'],
                         "sigma": 0.1, "max_gain": 1500}

RunT1 = False
RunT2 = False
T1T2_params = {"T1_step": 4, "T1_expts": 40, "T1_reps": 50, "T1_rounds": 20,
               "T2_step": 0.2, "T2_expts": 100, "T2_reps": 50, "T2_rounds": 20, "freq_shift": 0.5}

SingleShot = False
SS_params = {"Shots": 2000, "Readout_Time": 2.5, "ADC_Offset": 0.3}

SingleShot_2States = False
SS_params_2States = {"ground": 1, 'excited': 2, "Shots": 2500, "Readout_Time": 2.2, "ADC_Offset": 0.3}

SingleShot_MultipleBlobs = False
SS_params_blobs = {"check_12": True, "Shots": 2000, "Readout_Time": 2.5, "ADC_Offset": 0.3}




SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 5000, "gain_stop": 12000, "gain_pts": 8, "span": 1.2, "trans_pts": 13}

SingleShot_ReadoutOptimize_Higher = False
SS_R_params_H = {"ground": 1, "excited": 2, "gain_start": 5000, "gain_stop": 12000, "gain_pts": 8, "span": 1.2, "trans_pts": 13}

SingleShot_QubitOptimize = False
SS_Q_params = {"q_gain_span": 400, "q_gain_pts": 9, "q_freq_span": 4, "q_freq_pts": 13}

SingleShot_QubitOptimize_Higher = True
SS_Q_params = {"ground": 1, "excited": 2, "q_gain_span": 400, "q_gain_pts": 9, "q_freq_span": 3, "q_freq_pts": 13}


RunChiShift = False
ChiShift_Params = {'pulse_expt': {'check_12': True},
                   'qubit_freq01': Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency'], 'qubit_gain01': 1670 // 2,
                   'qubit_freq12':  Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency'],  'qubit_gain12': 1670 // 2}


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}


cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']


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

#### update the qubit and cavity attenuation
# cavityAtten.SetAttenuation(config["cav_Atten"], printOut=True)

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
    config["reps"] = 30  # want more reps and rounds for qubit data
    config["rounds"] = 30
    config["Gauss"] = Spec_relevant_params['Gauss']
    if Spec_relevant_params['Gauss']:
        config['sigma'] = Spec_relevant_params["sigma"]
        config["qubit_gain"] = Spec_relevant_params['gain']
    Instance_specSlice = QubitSpecSliceFF(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFF.acquire(Instance_specSlice)
    QubitSpecSliceFF.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFF.save_data(Instance_specSlice, data_specSlice)

expt_cfg = {
    "step": 2 * Spec_relevant_params_Higher["SpecSpan"] / Spec_relevant_params_Higher["SpecNumPoints"],
    "start": Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency'] - Spec_relevant_params_Higher["SpecSpan"],
    "expts": Spec_relevant_params_Higher["SpecNumPoints"]
}
config = config | expt_cfg
if Run2ToneSpec_2nd:
    config["reps"] = 30  # want more reps and rounds for qubit data
    config["rounds"] = 30
    config["Gauss"] = Spec_relevant_params_Higher['Gauss']
    config['sigma'] = Spec_relevant_params_Higher["sigma"]
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    if Spec_relevant_params_Higher['Gauss']:
        config["qubit_gain"] = Spec_relevant_params_Higher['gain']
    Instance_specSlice = SpecSliceFF_HigherExc(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                               outerFolder=outerFolder)
    data_specSlice = SpecSliceFF_HigherExc.acquire(Instance_specSlice)
    SpecSliceFF_HigherExc.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    SpecSliceFF_HigherExc.save_data(Instance_specSlice, data_specSlice)

# Amplitude Rabi
if RunAmplitudeRabi:
    number_of_steps = 31
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 20,
                    "sigma": Amplitude_Rabi_params["sigma"], "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": 300}
    config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
    iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
    AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)


if RunAmplitudeRabi_2nd:
    number_of_steps = 31
    step = int(Amplitude_Rabi_params_2nd["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 20,
                    "sigma": Amplitude_Rabi_params_2nd["sigma"],
                    "relax_delay": 300}
    config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    iAmpRabi = AmplitudeRabiFF_HigherExc(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFF_HigherExc.acquire(iAmpRabi)
    AmplitudeRabiFF_HigherExc.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFF_HigherExc.save_data(iAmpRabi, dAmpRabi)
config["sigma"] = Amplitude_Rabi_params["sigma"]

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

if RunChiShift:
    config =  config | ChiShift_Params
    iChi = ChiShift(path="ChiShift", cfg=config,soc=soc,soccfg=soccfg,
                                      outerFolder=outerFolder)
    dChi= ChiShift.acquire(iChi)
    ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
    ChiShift.save_data(iChi, dChi)


UpdateConfig = {
    ###### cavity
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "read_pulse_style": "const", # --Fixed
    "readout_length": SS_params["Readout_Time"], # us (length of the pulse applied)
    "adc_trig_offset": SS_params["ADC_Offset"],
    "pulse_gain": cavity_gain, # [DAC units]
    ##### qubit spec parameters
    "qubit_pulse_style": "arb",
    "sigma": config["sigma"],  ### units us, define a 20ns sigma
    "qubit_gain": qubit_gain,
    "f_ge": qubit_frequency_center,
    ##### define shots
    "shots": SS_params["Shots"], ### this gets turned into "reps"
    "relax_delay": 200,  # us
}

config = BaseConfig | UpdateConfig
config["FF_Qubits"] = FF_Qubits

print(config)
if SingleShot:
    Instance_SingleShotProgram = SingleShotProgramFF(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFF.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFF.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFF.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFF.save_config(Instance_SingleShotProgram)


if SingleShot_2States:
    config['pulse_expt'] = {"pulse_01": False, "pulse_12": False}
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
    config["readout_length"] = SS_params_2States["Readout_Time"] # us (length of the pulse applied)
    config["adc_trig_offset"] = SS_params_2States["ADC_Offset"]
    Instance_SingleShotProgram = SingleShotProgramFF_2States(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFF_2States.acquire(Instance_SingleShotProgram,
                                                                 ground_pulse=SS_params_2States["ground"],
                                                                 excited_pulse=SS_params_2States["excited"])
    # print(data_SingleShotProgram)
    SingleShotProgramFF_2States.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFF_2States.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFF_2States.save_config(Instance_SingleShotProgram)

if SingleShot_MultipleBlobs:
    config['pulse_expt'] = {"pulse_01": False, "pulse_12": False, "check_12": SS_params_blobs['check_12']}
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
    config["readout_length"] = SS_params_blobs["Readout_Time"] # us (length of the pulse applied)
    config["adc_trig_offset"]=  SS_params_blobs["ADC_Offset"]
    Instance_SingleShotProgram = SingleShotProgramFF_HigherLevels(path="SingleShot_HigherLevels", outerFolder=outerFolder, cfg=config,
                                                     soc=soc, soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFF_HigherLevels.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFF_HigherLevels.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFF_HigherLevels.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFF_HigherLevels.save_config(Instance_SingleShotProgram)

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
        "trans_freq_start": config["pulse_freq"] - span / 2, #249.6,
        "trans_freq_stop": config["pulse_freq"] + span / 2, #250.3,
        "TransNumPoints": cav_trans_pts,
    }
    config = config | exp_parameters
    # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFF(path="SingleShot_OptReadout", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize, cavityAtten = cavityAtten)
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    ReadOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)
    config["pulse_freq"] = resonator_frequency_center

if SingleShot_QubitOptimize:
    q_gain_span = SS_Q_params['q_gain_span']
    q_gain_pts = SS_Q_params['q_gain_pts']
    q_freq_pts = SS_Q_params['q_freq_pts']
    q_freq_span = SS_Q_params['q_freq_span']
    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": qubit_gain - q_gain_span / 2,
        "qubit_gain_Stop": qubit_gain + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_center - q_freq_span / 2, #249.6,
        "qubit_freq_stop": qubit_frequency_center + q_freq_span / 2, #250.3,
        "QubitNumPoints": q_freq_pts,
    }
    config = config | exp_parameters

    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFF(path="SingleShot_OptQubit", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFF.acquire(Instance_SingleShotOptimize, cavityAtten = cavityAtten)
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFF.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    QubitPulseOpt_wSingleShotFF.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFF.save_config(Instance_SingleShotOptimize)

if SingleShot_QubitOptimize_Higher:
    q_gain_span = SS_Q_params['q_gain_span']
    q_gain_pts = SS_Q_params['q_gain_pts']
    q_freq_pts = SS_Q_params['q_freq_pts']
    q_freq_span = SS_Q_params['q_freq_span']
    ground_pulse = SS_Q_params['ground']
    excited_pulse = SS_Q_params['excited']
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
    if excited_pulse == 2:
        qubit_gain_ = config['qubit_gain12']
        qubit_frequency_center_ = config['qubit_freq12']
    else:
        qubit_gain_ = config['qubit_gain01']
        qubit_frequency_center_ = config['qubit_freq01']

    exp_parameters = {
        ###### cavity
        "qubit_gain_Start": qubit_gain_ - q_gain_span / 2,
        "qubit_gain_Stop": qubit_gain_ + q_gain_span / 2,
        "qubit_gain_Points": q_gain_pts,
        "qubit_freq_start": qubit_frequency_center_ - q_freq_span / 2, #249.6,
        "qubit_freq_stop": qubit_frequency_center_ + q_freq_span / 2, #250.3,
        "QubitNumPoints": q_freq_pts,
    }
    print(exp_parameters)
    config = config | exp_parameters

    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFF_Higher(path="SingleShot_OptQubit", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFF_Higher.acquire(Instance_SingleShotOptimize,
                                                                        ground = ground_pulse, excited = excited_pulse)
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFF_Higher.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    QubitPulseOpt_wSingleShotFF_Higher.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFF_Higher.save_config(Instance_SingleShotOptimize)

if SingleShot_ReadoutOptimize_Higher:
    span = SS_R_params_H['span']
    cav_gain_start = SS_R_params_H['gain_start']
    cav_gain_stop = SS_R_params_H['gain_stop']
    cav_gain_pts = SS_R_params_H['gain_pts']
    cav_trans_pts = SS_R_params_H['trans_pts']
    ground_pulse = SS_R_params_H['ground']
    excited_pulse = SS_R_params_H['excited']

    exp_parameters = {
        ###### cavity
        "cav_gain_Start": cav_gain_start,
        "cav_gain_Stop": cav_gain_stop,
        "cav_gain_Points": cav_gain_pts,
        "trans_freq_start": config["pulse_freq"] - span / 2, #249.6,
        "trans_freq_stop": config["pulse_freq"] + span / 2, #250.3,
        "TransNumPoints": cav_trans_pts,
    }

    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
    if excited_pulse == 2:
        qubit_gain_ = config['qubit_gain12']
        qubit_frequency_center_ = config['qubit_freq12']
    else:
        qubit_gain_ = config['qubit_gain01']
        qubit_frequency_center_ = config['qubit_freq01']

    config = config | exp_parameters

    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFF_Higher(path="SingleShot_OptReadout", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF_Higher.acquire(Instance_SingleShotOptimize,
                                                                        ground = ground_pulse, excited = excited_pulse)
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFF_Higher.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    ReadOpt_wSingleShotFF_Higher.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFF_Higher.save_config(Instance_SingleShotOptimize)