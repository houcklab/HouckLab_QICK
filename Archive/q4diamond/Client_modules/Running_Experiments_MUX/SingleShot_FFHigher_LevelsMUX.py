# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.Running_Experiments_MUX.MUXInitialize import *

from q4diamond.Client_modules.Experimental_Scripts_MUX.mTransmissionFFMUX import CavitySpecFFMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mSpecSliceFFMUX import QubitSpecSliceFFMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mAmplitudeRabiFFMUX import AmplitudeRabiFFMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFFMUX import SingleShotProgramFFMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mOptimizeReadoutandPulse_FFMUX import *
from q4diamond.Client_modules.Experimental_Scripts_MUX.mAmplitudeRabiFF_HigherLevelsMUX import AmplitudeRabiFF_HigherExcMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mSpecSliceFF_HigherLevelsMUX import SpecSliceFF_HigherExcMUX
from q4diamond.Client_modules.Experimental_Scripts_MUX.mSingleShotProgramFF_HigherLevelsMUX import SingleShotProgramFF_2StatesMUX, SingleShotProgramFF_HigherLevelsMUX

from q4diamond.Client_modules.Experimental_Scripts_MUX.mT1_TwoPulsesSS import T1_TwoPulseMUXSS
from q4diamond.Client_modules.Experimental_Scripts_MUX.mT2R_TwoPulses import T2R_2PulseMUX, T2R_2PulseMUX_NoUpdate
from q4diamond.Client_modules.Experiment_Scripts.mChiShift import ChiShift

#### define the saving path
outerFolder = "Z:\Jeronimo\Measurements\RFSOC_4Qubit_0F\\"

yoko69.rampstep = 0.0005
yoko70.rampstep = 0.0005
yoko71.rampstep = 0.0005
yoko72.rampstep = 0.0005

# yoko69.SetVoltage(-0.1214)
# yoko70.SetVoltage(-0.2226)
# yoko71.SetVoltage(-0.2905)
# yoko72.SetVoltage(0.2407)

mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {
        # 'Readout': {'Frequency': 6953 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
        #               "FF_Gains": [-15900, 0, 0, 0]}, #01 optimization
            'Readout': {'Frequency': 6952.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                      "FF_Gains": [-15900, 0, 0, 0]}, #12 optimization
          'Qubit01': {'Frequency': 4682.6 , 'Gain': 1180},
          'Qubit12': {'Frequency':4530.5, 'Gain': 790},
          'Pulse_FF': [-9800, 0, 0, 0]},
    '2': {
        # 'Readout': {'Frequency': 7056.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
        #               "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3}, #Optimize 01
        'Readout': {'Frequency': 7055.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
                    "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},  #Optimize 12
          'Qubit01':  {'Frequency': 4802.6, 'Gain': 830},
          'Qubit12': {'Frequency': 4646.6, 'Gain': 1270},
          'Pulse_FF': [0, 13000, 0, 0]},
    '3': {
        'Readout': {'Frequency': 7117.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6500,
                    "FF_Gains": [0, 0, 17000, 0]},
        'Readout': {'Frequency': 7117.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6700,
                    "FF_Gains": [0, 0, 17000, 0]},
          'Qubit01': {'Frequency': 4807.6, 'Gain': 870},
          'Qubit12': {'Frequency': 4651.6, 'Gain': 1340},
          'Pulse_FF': [0, 0, 13000, 0]},
    '4': {
        # 'Readout': {'Frequency': 7250.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6500,
        # "FF_Gains": [0, 0, 0, -25000]},   #optimize 01
        'Readout': {'Frequency': 7249.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                    "FF_Gains": [0, 0, 0, -25000]},   #Optimize 12
        'Qubit01': {'Frequency': 4910.4, 'Gain': 2150},
          'Qubit12': {'Frequency': 4754.3, 'Gain': 720},
          'Pulse_FF': [0, 0, 0, -21000]}
    }

#Qubit Parameters for physics
mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {
        # 'Readout': {'Frequency': 6953 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
        #               "FF_Gains": [-15900, 0, 0, 0]}, #01 optimization
            'Readout': {'Frequency': 6952.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                      "FF_Gains": [-15900, 0, 0, 0]}, #12 optimization
          'Qubit01': {'Frequency': 4682.6 , 'Gain': 1180},
          'Qubit12': {'Frequency':4530.5, 'Gain': 790},
          'Pulse_FF': [-9800, 0, 0, 0]},
    '2': {
        'Readout': {'Frequency': 7056.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
                      "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3}, #Optimize 01
        # 'Readout': {'Frequency': 7055.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
        #             "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},  #Optimize 12
          'Qubit01':  {'Frequency': 4802.6, 'Gain': 830},
          'Qubit12': {'Frequency': 4646.6, 'Gain': 1270},
          'Pulse_FF': [0, 13000, 0, 0]},
    '3': {
        'Readout': {'Frequency': 7117.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6500,
                    "FF_Gains": [0, 0, 17000, 0]},
        # 'Readout': {'Frequency': 7117.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6700,
        #             "FF_Gains": [0, 0, 17000, 0]},
          'Qubit01': {'Frequency': 4807.6, 'Gain': 870},
          'Qubit12': {'Frequency': 4651.6, 'Gain': 1340},
          'Pulse_FF': [0, 0, 13000, 0]},
    '4': {
        'Readout': {'Frequency': 7250.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6500,
        "FF_Gains": [0, 0, 0, -25000]},   #optimize 01
        # 'Readout': {'Frequency': 7249.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
        #             "FF_Gains": [0, 0, 0, -25000]},   #Optimize 12
        'Qubit01': {'Frequency': 4910.4, 'Gain': 2150},
          'Qubit12': {'Frequency': 4754.3, 'Gain': 720},
          'Pulse_FF': [0, 0, 0, -21000]}
    }

# # #Reading out T1T2 parameters at physics frequency
# mixer_freq = 500
# BaseConfig["mixer_freq"] = mixer_freq
# Qubit_Parameters = {
#     '1': {
#         # 'Readout': {'Frequency': 6953 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
#         #               "FF_Gains": [-15900, 0, 0, 0]}, #01 optimization
#             'Readout': {'Frequency': 6952.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
#                       "FF_Gains": [0, 0, 0, 0]}, #12 optimization
#           'Qubit01': {'Frequency': 4449.1 , 'Gain': 400},
#           'Qubit12': {'Frequency':4292, 'Gain': 930},
#           'Pulse_FF': [0, 0, 0, 0]},
#     '2': {
#         'Readout': {'Frequency': 7055.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#                       "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3}, #Optimize 01
#         # 'Readout': {'Frequency': 7055.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
#         #             "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},  #Optimize 12
#           'Qubit01':  {'Frequency': 4449.8, 'Gain': 400},
#           'Qubit12': {'Frequency': 4292.3, 'Gain': 860},
#           'Pulse_FF': [0, 0, 0, 0]},
#     '3': {
#         'Readout': {'Frequency': 7117.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6500,
#                     "FF_Gains": [0, 0, 0, 0]},
#         # 'Readout': {'Frequency': 7117.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6700,
#         #             "FF_Gains": [0, 0, 17000, 0]},
#           'Qubit01': {'Frequency': 4449.2, 'Gain': 750},
#           'Qubit12': {'Frequency': 4290, 'Gain': 830},
#           'Pulse_FF': [0, 0, 0, 0]},
#     '4': {
#         'Readout': {'Frequency': 7249.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6500,
#         "FF_Gains": [0, 0, 0, 0]},   #optimize 01
#         # 'Readout': {'Frequency': 7249.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#         #             "FF_Gains": [0, 0, 0, -25000]},   #Optimize 12
#         'Qubit01': {'Frequency': 4448.2, 'Gain': 550},
#           'Qubit12': {'Frequency': 4289.8, 'Gain': 840},
#           'Pulse_FF': [0, 0, 0, 0]}
#     }

# yoko69.SetVoltage(-0.1368)
# yoko70.SetVoltage(-0.1542)
# yoko71.SetVoltage(-0.2343)
# yoko72.SetVoltage(0.1055)
#Reading out T1T2 parameters at physics frequency
# mixer_freq = 500
# BaseConfig["mixer_freq"] = mixer_freq
# Qubit_Parameters = {
#     '1': {
#         'Readout': {'Frequency': 6962.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
#                       "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': False},
#         'Readout': {'Frequency': 6962.3 - 0.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
#                     "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': False},
#           'Qubit01': {'Frequency': 4449.3, 'Gain': 900},
#           'Qubit12': {'Frequency':4291.4, 'Gain': 1750 * 0},
#           'Pulse_FF': [0, 0, 0, 0]},
#     '2': {
#         'Readout': {'Frequency': 7033.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4500,
#                       "FF_Gains": [0, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
#         'Readout': {'Frequency': 7033.4 - 0.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#                     "FF_Gains": [0, -5000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
#           'Qubit01':  {'Frequency': 4450.5, 'Gain': 920},
#           'Qubit12': {'Frequency': 4292.4, 'Gain': 1700 * 0},
#           'Pulse_FF': [0, 0, 0, 0]},
#     '3': {
#         'Readout': {'Frequency': 7104.4 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#                       "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
#         'Readout': {'Frequency': 7104.4 - 0.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#                     "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
#           'Qubit01': {'Frequency': 4448.3, 'Gain': 2000},
#           'Qubit12': {'Frequency': 4290.8, 'Gain': 2000 * 0},
#           'Pulse_FF': [0, 0, 0, 0]},
#     '4': {
#         'Readout': {'Frequency': 7230.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#                       "FF_Gains": [0, 0, 0, 0], 'cavmin': True},
#         'Readout': {'Frequency': 7230.1 - 0.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#                     "FF_Gains": [0, 0, 0, 0], 'cavmin': True}, #Optimize 12
#           'Qubit01': {'Frequency': 4448.9, 'Gain': 1250},
#           'Qubit12': {'Frequency': 4291.6, 'Gain': 1900 },
#           'Pulse_FF': [0, 0, 0, 0]}
#     }


# yoko69.SetVoltage(-0.14)
# yoko70.SetVoltage(0.0375)
# yoko71.SetVoltage(-0.0147)
# yoko72.SetVoltage(-0.1099)
# Qubit_Readout = [1]
# Qubit_Pulse = 1

# yoko69.SetVoltage(0.0662)
# yoko70.SetVoltage(-0.1472)
# yoko71.SetVoltage(-0.005)
# yoko72.SetVoltage(-0.0965)
# Qubit_Readout = [2]
# Qubit_Pulse = 2

# yoko69.SetVoltage(0.0508)
# yoko70.SetVoltage(0.0363)
# yoko71.SetVoltage(-0.2416)
# yoko72.SetVoltage(-0.1127)
# Qubit_Readout = [3]
# Qubit_Pulse = 3

# yoko69.SetVoltage(0.0655)
# yoko70.SetVoltage(0.0464)
# yoko71.SetVoltage(-0.0073)
# yoko72.SetVoltage(0.1141)
# Qubit_Readout = [4]
# Qubit_Pulse = 4


# yoko69.SetVoltage(-0.1368)
# yoko70.SetVoltage(-0.1542)
# yoko71.SetVoltage(-0.2343)
# yoko72.SetVoltage(0.1055)
# #Reading out T1T2 parameters at physics frequency
# mixer_freq = 500
# BaseConfig["mixer_freq"] = mixer_freq
# Qubit_Parameters = {
#     '1': {
#         'Readout': {'Frequency': 6962.8 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
#                       "FF_Gains": [15900, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': False},
#         'Readout': {'Frequency': 6962.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
#                     "FF_Gains": [15900, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': False},
#           'Qubit01': {'Frequency': 4688.7, 'Gain': 1100},
#           'Qubit12': {'Frequency':4535.1, 'Gain': 850},
#           'Pulse_FF': [9500, 0, 0, 0]},
#     '2': {
#         'Readout': {'Frequency': 7034.2 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 4500,
#                       "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
#         'Readout': {'Frequency': 7033.45 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#                     "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
#           'Qubit01':  {'Frequency': 4811.2, 'Gain': 860},
#           'Qubit12': {'Frequency': 4654.5, 'Gain': 1300},
#           'Pulse_FF': [0, 13000, 0, 0]},
#     '3': {
#         'Readout': {'Frequency': 7105.0 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#                       "FF_Gains": [0, 0, 20000, 0], 'cavmin': True},
#         'Readout': {'Frequency': 7104.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#                     "FF_Gains": [0, 0, 30000, 0], 'cavmin': True},
#           'Qubit01': {'Frequency': 4806.1, 'Gain': 980},
#           'Qubit12': {'Frequency': 4649.5, 'Gain': 1470},
#           'Pulse_FF': [0, 0, 15000, 0]},
#     '4': {
#         'Readout': {'Frequency': 7230.7 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
#                       "FF_Gains": [0, 0, 0, -20000], 'cavmin': True},
#         'Readout': {'Frequency': 7230. - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
#                     "FF_Gains": [0, 0, 0, -20000], 'cavmin': True}, #Optimize 12
#           'Qubit01': {'Frequency': 4761.8, 'Gain': 1250},
#           'Qubit12': {'Frequency': 4606.5, 'Gain': 2000},
#           'Pulse_FF': [0, 0, 0, -13000]}
#     }

yoko69.SetVoltage(-0.1167)
yoko70.SetVoltage(-0.1266)
yoko71.SetVoltage(-0.2437)
yoko72.SetVoltage(0.1134)
#Reading out T1T2 parameters at physics frequency
mixer_freq = 500
BaseConfig["mixer_freq"] = mixer_freq
Qubit_Parameters = {
    '1': {
        'Readout': {'Frequency': 6962.3 - 0. - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                    "FF_Gains": [15900, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
        'Readout': {'Frequency': 6962.3 - 0.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 7000,
                    "FF_Gains": [15900, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01': {'Frequency': 4688.3, 'Gain': 1100},
          'Qubit12': {'Frequency':4534.8, 'Gain': 820},
          'Pulse_FF': [9500, 0, 0, 0]},
    '2': {
        'Readout': {'Frequency': 7033.4 + 0.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5700,
                    "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
        # 'Readout': {'Frequency': 7033.45 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
        #             "FF_Gains": [0, 20000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3, 'cavmin': True},
          'Qubit01':  {'Frequency': 4811.2, 'Gain': 860},
          'Qubit12': {'Frequency': 4654.5, 'Gain': 1300},
          'Pulse_FF': [0, 13000, 0, 0]},
    '3': {
        'Readout': {'Frequency': 7104.4 + 0.3 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5700,
                    "FF_Gains": [0, 0, 30000, 0], 'cavmin': True},
        # 'Readout': {'Frequency': 7104.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 6000,
        #             "FF_Gains": [0, 0, 30000, 0], 'cavmin': True},
          'Qubit01': {'Frequency': 4806.1, 'Gain': 980},
          'Qubit12': {'Frequency': 4649.5, 'Gain': 1470},
          'Pulse_FF': [0, 0, 15000, 0]},
    '4': {
        # 'Readout': {'Frequency': 7230. + 0.5 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5500,
        #             "FF_Gains": [0, 0, 0, -20000], 'cavmin': True}, #Optimize 12
        'Readout': {'Frequency': 7230.1 - mixer_freq - BaseConfig["cavity_LO"] / 1e6, 'Gain': 5000,
                    "FF_Gains": [0, 0, 0, -20000], 'cavmin': True}, #Optimize 12
          'Qubit01': {'Frequency': 4761.8, 'Gain': 1250},
          'Qubit12': {'Frequency': 4606.5, 'Gain': 2000},
          'Pulse_FF': [0, 0, 0, -13000]}
    }






#
Qubit_Readout = [1]
Qubit_Pulse = 1
# expt
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = 0

FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['FF_Gains']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']

BaseConfig['ro_chs'] = [i for i in range(len(Qubit_Readout))]

RunTransmissionSweep = False  # determine cavity frequency
Run2ToneSpec = False
sigma = 0.05
Spec_relevant_params = {"qubit_gain": 300, "SpecSpan": 10, "SpecNumPoints": 61, 'Gauss': True, "sigma":sigma,
                        "gain": 950}

RunAmplitudeRabi = False
Amplitude_Rabi_params = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency'],
                         "sigma": sigma, "max_gain": 3000}

Run2ToneSpec_2nd = False
Spec_relevant_params_Higher = {"qubit_gain": 150, "SpecSpan": 10, "SpecNumPoints": 61, 'Gauss': True, "sigma": sigma,
                    "gain": 700}

RunAmplitudeRabi_2nd = False
Amplitude_Rabi_params_2nd = {"qubit_freq": Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency'],
                         "sigma": sigma, "max_gain": 2500}

RunT1 = False
RunT2 = False
RunT1SS = False
T1T2_params = {"SecondPulse": 1, "T1_step": 4,"T1_expts": 60,"T1_reps": 50,"T1_rounds": 20,
                "T2_step":0.00232515*22 * 2,"T2_expts":100,"T2_reps":50,"T2_rounds":20,"freq_shift":1.4}

SingleShot = False
SS_params = {"Shots": 2000, "Readout_Time": 2.5, "ADC_Offset": 0.3}

SingleShot_2States = False
SS_params_2States = {"ground": 1, 'excited': 2, "Shots": 2500, "Readout_Time": 2.5, "ADC_Offset": 0.3}

SingleShot_MultipleBlobs = False
SS_params_blobs = {"check_12": True, "Shots": 2000, "Readout_Time": 2.5, "ADC_Offset": 0.3}




SingleShot_ReadoutOptimize = False
SS_R_params = {"gain_start": 3000, "gain_stop": 10000, "gain_pts": 8, "span": 1.2, "trans_pts": 13}

SingleShot_ReadoutOptimize_Higher = False
SS_R_params_H = {"ground": 1, "excited": 2, "gain_start": 3000, "gain_stop": 10000, "gain_pts": 8, "span": 1.2, "trans_pts": 13}

SingleShot_QubitOptimize = False
SS_Q_params = {"q_gain_span": 400, "q_gain_pts": 9, "q_freq_span": 3, "q_freq_pts": 13}

SingleShot_QubitOptimize_Higher = True
SS_Q_params = {"ground": 1, "excited": 2, "q_gain_span": 400, "q_gain_pts": 9, "q_freq_span": 5, "q_freq_pts": 13}


RunChiShift = False
ChiShift_Params = {'pulse_expt': {'check_12': True},
                   'qubit_freq01': Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency'], 'qubit_gain01': 1670 // 2,
                   'qubit_freq12':  Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency'],  'qubit_gain12': 1670 // 2}


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}


# cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
# resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
# qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
# qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']

cavity_gain = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout[0])]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
resonator_frequencies = [Qubit_Parameters[str(Q_R)]['Readout']['Frequency'] for Q_R in Qubit_Readout]
gains = [Qubit_Parameters[str(Q_R)]['Readout']['Gain'] / 32000. * len(Qubit_Readout) for Q_R in Qubit_Readout]



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
    if cavity_min:
        config["pulse_freq"] = Instance_trans.peakFreq_min - mixer_freq
    else:
        config["pulse_freq"] = Instance_trans.peakFreq_max - mixer_freq
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
    Instance_specSlice = QubitSpecSliceFFMUX(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                          outerFolder=outerFolder)
    data_specSlice = QubitSpecSliceFFMUX.acquire(Instance_specSlice)
    QubitSpecSliceFFMUX.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    QubitSpecSliceFFMUX.save_data(Instance_specSlice, data_specSlice)

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
    Instance_specSlice = SpecSliceFF_HigherExcMUX(path="QubitSpecFF", cfg=config, soc=soc, soccfg=soccfg,
                                               outerFolder=outerFolder)
    data_specSlice = SpecSliceFF_HigherExcMUX.acquire(Instance_specSlice)
    SpecSliceFF_HigherExcMUX.display(Instance_specSlice, data_specSlice, plotDisp=True, figNum=2)
    SpecSliceFF_HigherExcMUX.save_data(Instance_specSlice, data_specSlice)

# Amplitude Rabi
if RunAmplitudeRabi:
    number_of_steps = 31
    step = int(Amplitude_Rabi_params["max_gain"] / number_of_steps)
    ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps, "reps": 20, "rounds": 20,
                    "sigma": Amplitude_Rabi_params["sigma"], "f_ge": Amplitude_Rabi_params["qubit_freq"],
                    "relax_delay": 300}
    config = config | ARabi_config  ### note that UpdateConfig will overwrite elements in BaseConfig
    iAmpRabi = AmplitudeRabiFFMUX(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFFMUX.acquire(iAmpRabi)
    AmplitudeRabiFFMUX.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFFMUX.save_data(iAmpRabi, dAmpRabi)


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
    iAmpRabi = AmplitudeRabiFF_HigherExcMUX(path="AmplitudeRabi", cfg=config, soc=soc, soccfg=soccfg,
                               outerFolder=outerFolder)
    dAmpRabi = AmplitudeRabiFF_HigherExcMUX.acquire(iAmpRabi)
    AmplitudeRabiFF_HigherExcMUX.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
    AmplitudeRabiFF_HigherExcMUX.save_data(iAmpRabi, dAmpRabi)
config["sigma"] = Amplitude_Rabi_params["sigma"]

#
if RunT1:
    expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                "reps": T1T2_params["T1_reps"],
                "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain, "relax_delay": 200
                }
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
    config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT1 = T1_TwoPulseMUXSS(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT1 = T1_TwoPulseMUXSS.acquire(iT1)
    T1_TwoPulseMUXSS.display(iT1, dT1, plotDisp=True, figNum=2)
    T1_TwoPulseMUXSS.save_data(iT1, dT1)
if RunT2:
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency'] + T1T2_params["freq_shift"]
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
    T2R_cfg = {"start": 0, "step": T1T2_params["T2_step"], "phase_step": 0,
               "expts": T1T2_params["T2_expts"], "reps": T1T2_params["T2_reps"], "rounds": T1T2_params["T2_rounds"],
                "relax_delay": 200,
               }

    config = config | T2R_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig

    iT2R = T2R_2PulseMUX_NoUpdate(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT2R = T2R_2PulseMUX_NoUpdate.acquire(iT2R)
    T2R_2PulseMUX_NoUpdate.display(iT2R, dT2R, plotDisp=True, figNum=2)
    T2R_2PulseMUX_NoUpdate.save_data(iT2R, dT2R)
    #
    # import time
    # start = time.time()
    # n = 0
    # while time.time() - start < 60 * 60 * 11:
    #     soc.reset_gens()
    #     print(n)
    #     time.sleep(120)
    #     iT2R = T2R_2PulseMUX(path="T2R", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    #     dT2R = T2R_2PulseMUX.acquire(iT2R)
    #     T2R_2PulseMUX.display(iT2R, dT2R, plotDisp=False, figNum=2)
    #     T2R_2PulseMUX.save_data(iT2R, dT2R)
    #     n += 1
if RunChiShift:
    config =  config | ChiShift_Params
    iChi = ChiShift(path="ChiShift", cfg=config,soc=soc,soccfg=soccfg,
                                      outerFolder=outerFolder)
    dChi= ChiShift.acquire(iChi)
    ChiShift.display(iChi, dChi, plotDisp=True, figNum=1)
    ChiShift.save_data(iChi, dChi)

if type(Qubit_Pulse) != list:
    Qubit_Pulse = [Qubit_Pulse]
qubit_gains = [Qubit_Parameters[str(Q_R)]['Qubit01']['Gain'] for Q_R in Qubit_Pulse]
qubit_frequency_centers = [Qubit_Parameters[str(Q_R)]['Qubit01']['Frequency'] for Q_R in Qubit_Pulse]

UpdateConfig = {
    ###### cavity
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    "read_pulse_style": "const", # --Fixed
    "readout_length": SS_params["Readout_Time"], # us (length of the pulse applied)
    "adc_trig_offset": SS_params["ADC_Offset"],
    "pulse_gain": cavity_gain, # [DAC units]
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
config['Read_Indeces'] = Qubit_Readout

if RunT1SS:
    config['pulse_expt'] = {"pulse_01": False, "pulse_12": False}
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Gain']
    config["readout_length"] = SS_params_2States["Readout_Time"]  # us (length of the pulse applied)
    config["adc_trig_offset"] = SS_params_2States["ADC_Offset"]

    Instance_SingleShotProgram = SingleShotProgramFF_2StatesMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                                soc=soc, soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFF_2StatesMUX.acquire(Instance_SingleShotProgram,
                                                                    ground_pulse=T1T2_params["SecondPulse"] - 1,
                                                                    excited_pulse=T1T2_params["SecondPulse"])
    data_SingleShotProgram = SingleShotProgramFF_2StatesMUX.analyze(Instance_SingleShotProgram, data_SingleShotProgram)

    angle, threshold = data_SingleShotProgram['angle'], data_SingleShotProgram['threshold']

    SingleShotProgramFF_2StatesMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFF_2StatesMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)


    expt_cfg = {"start": 0, "step": T1T2_params["T1_step"], "expts": T1T2_params["T1_expts"],
                "reps": T1T2_params["T1_reps"],
                "rounds": T1T2_params["T1_rounds"], "pi_gain": qubit_gain, "relax_delay": 200
                }
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Gain']
    config = config | expt_cfg  ### note that UpdateConfig will overwrite elements in BaseConfig
    iT1 = T1_TwoPulseMUXSS(path="T1", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dT1 = T1_TwoPulseMUXSS.acquire(iT1, angle=angle, threshold=threshold, excited_pulse = T1T2_params["SecondPulse"] )
    T1_TwoPulseMUXSS.display(iT1, dT1, plotDisp=True, figNum=2)
    T1_TwoPulseMUXSS.save_data(iT1, dT1)


if SingleShot_2States:
    config['pulse_expt'] = {"pulse_01": False, "pulse_12": False}
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Gain']
    config["readout_length"] = SS_params_2States["Readout_Time"] # us (length of the pulse applied)
    config["adc_trig_offset"] = SS_params_2States["ADC_Offset"]

    Instance_SingleShotProgram = SingleShotProgramFF_2StatesMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFF_2StatesMUX.acquire(Instance_SingleShotProgram,
                                                                 ground_pulse=SS_params_2States["ground"],
                                                                 excited_pulse=SS_params_2States["excited"])
    # print(data_SingleShotProgram)
    SingleShotProgramFF_2StatesMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFF_2StatesMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFF_2StatesMUX.save_config(Instance_SingleShotProgram)


print(config)
if SingleShot:
    Instance_SingleShotProgram = SingleShotProgramFFMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFFMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFFMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFFMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFFMUX.save_config(Instance_SingleShotProgram)


if SingleShot_2States:
    config['pulse_expt'] = {"pulse_01": False, "pulse_12": False}
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Gain']
    config["readout_length"] = SS_params_2States["Readout_Time"] # us (length of the pulse applied)
    config["adc_trig_offset"] = SS_params_2States["ADC_Offset"]

    Instance_SingleShotProgram = SingleShotProgramFF_2StatesMUX(path="SingleShot", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFF_2StatesMUX.acquire(Instance_SingleShotProgram,
                                                                 ground_pulse=SS_params_2States["ground"],
                                                                 excited_pulse=SS_params_2States["excited"])
    # print(data_SingleShotProgram)
    SingleShotProgramFF_2StatesMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFF_2StatesMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFF_2StatesMUX.save_config(Instance_SingleShotProgram)

if SingleShot_MultipleBlobs:
    config['pulse_expt'] = {"pulse_01": False, "pulse_12": False, "check_12": SS_params_blobs['check_12']}
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Gain']
    config["readout_length"] = SS_params_blobs["Readout_Time"] # us (length of the pulse applied)
    config["adc_trig_offset"]=  SS_params_blobs["ADC_Offset"]
    Instance_SingleShotProgram = SingleShotProgramFF_HigherLevelsMUX(path="SingleShot_HigherLevels", outerFolder=outerFolder, cfg=config,
                                                     soc=soc, soccfg=soccfg)
    data_SingleShotProgram = SingleShotProgramFF_HigherLevelsMUX.acquire(Instance_SingleShotProgram)
    # print(data_SingleShotProgram)
    SingleShotProgramFF_HigherLevelsMUX.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

    SingleShotProgramFF_HigherLevelsMUX.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
    SingleShotProgramFF_HigherLevelsMUX.save_config(Instance_SingleShotProgram)

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
    Qubit_Pulse_Index = 0
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


if SingleShot_QubitOptimize_Higher:
    q_gain_span = SS_Q_params['q_gain_span']
    q_gain_pts = SS_Q_params['q_gain_pts']
    q_freq_pts = SS_Q_params['q_freq_pts']
    q_freq_span = SS_Q_params['q_freq_span']
    ground_pulse = SS_Q_params['ground']
    excited_pulse = SS_Q_params['excited']
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Gain']
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
    Instance_SingleShotOptimize = QubitPulseOpt_wSingleShotFF_HigherMUX(path="SingleShot_OptQubit", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = QubitPulseOpt_wSingleShotFF_HigherMUX.acquire(Instance_SingleShotOptimize,
                                                                        ground = ground_pulse, excited = excited_pulse)
    # print(data_SingleShotProgram)
    QubitPulseOpt_wSingleShotFF_HigherMUX.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    QubitPulseOpt_wSingleShotFF_HigherMUX.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    QubitPulseOpt_wSingleShotFF_HigherMUX.save_config(Instance_SingleShotOptimize)

if SingleShot_ReadoutOptimize_Higher:
    span = SS_R_params_H['span']
    cav_gain_start = SS_R_params_H['gain_start']
    cav_gain_stop = SS_R_params_H['gain_stop']
    cav_gain_pts = SS_R_params_H['gain_pts']
    cav_trans_pts = SS_R_params_H['trans_pts']

    span = SS_R_params['span']
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
        "trans_freq_start": config["mixer_freq"] - span / 2, #249.6,
        "trans_freq_stop": config["mixer_freq"] + span / 2, #250.3,
        "TransNumPoints": cav_trans_pts,
    }

    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse[0])]['Qubit12']['Gain']
    if excited_pulse == 2:
        qubit_gain_ = config['qubit_gain12']
        qubit_frequency_center_ = config['qubit_freq12']
    else:
        qubit_gain_ = config['qubit_gain01']
        qubit_frequency_center_ = config['qubit_freq01']

    config = config | exp_parameters

    # # Now lets optimize powers and readout frequencies
    Instance_SingleShotOptimize = ReadOpt_wSingleShotFF_HigherMUX(path="SingleShot_OptReadout", outerFolder=outerFolder, cfg=config,soc=soc,soccfg=soccfg)
    data_SingleShotProgramOptimize = ReadOpt_wSingleShotFF_HigherMUX.acquire(Instance_SingleShotOptimize,
                                                                        ground = ground_pulse, excited = excited_pulse)
    # print(data_SingleShotProgram)
    ReadOpt_wSingleShotFF_HigherMUX.display(Instance_SingleShotOptimize, data_SingleShotProgramOptimize, plotDisp=True)

    ReadOpt_wSingleShotFF_HigherMUX.save_data(Instance_SingleShotOptimize, data_SingleShotProgramOptimize)
    ReadOpt_wSingleShotFF_HigherMUX.save_config(Instance_SingleShotOptimize)