# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillations_2nd_SS import WalkFFSS
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillations_GainSweep import Oscillations_Gain
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillations_2nd_GainSweep import Oscillations_Gain_2nd, Oscillations_Gain_2nd_SS
from q4diamond.Client_modules.Experiment_Scripts.mSingleShotProgramFF_HigherLevels import SingleShotProgramFF_2States

print(soc)

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

# yoko69.SetVoltage(-0.0887)
# yoko70.SetVoltage(-0.2419)
# yoko71.SetVoltage(-0.0012)
# yoko72.SetVoltage(0.2829)

# yoko69.SetVoltage(-0.0999)
# yoko70.SetVoltage(-0.2528)
# yoko71.SetVoltage(-0.3299)
# yoko72.SetVoltage(0.2747)

# yoko69.SetVoltage(-0.0928)
# yoko70.SetVoltage(-0.2451)
# yoko71.SetVoltage(-0.315)
# yoko72.SetVoltage(0.2793)

#Readout Qubit Params

Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6952.5, 'Gain': 11500, "FF_Gains": [-11000, 0, 0, 0]},
          'Qubit01': {'Frequency': 4664.1, 'Gain': 1380},
          'Qubit12': {'Frequency': 4510.7, 'Gain': 640 * 0},
          'Pulse_FF': [-11000, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7055.6, 'Gain': 8000, "FF_Gains": [0, 11000, 0, 0]},
          'Qubit01': {'Frequency': 4693, 'Gain': 1000},
          'Qubit12': {'Frequency': 4538.2 , 'Gain': 790 * 0},
          'Pulse_FF': [0, 11000, 0, 0]},
    '3': {'Readout': {'Frequency': 7117.1, 'Gain': 8000, "FF_Gains": [0, 0, 11000, 0]},
          'Qubit01': {'Frequency': 4692.7, 'Gain': 1330},
          'Qubit12': {'Frequency': 4538.4, 'Gain': 680 * 0},
          'Pulse_FF': [0, 0, 11000, 0]},
    '4': {'Readout': {'Frequency': 7249.6, 'Gain': 7500, "FF_Gains": [0, 0, 0, -14000]},
          'Qubit01': {'Frequency': 4670.5, 'Gain': 1500},
          'Qubit12': {'Frequency': 4516.3, 'Gain': 820 * 0},
          'Pulse_FF': [0, 0, 0, -14000] }
    }

Qubit_Readout = 4
Qubit_Pulse = 1
# Readout

# expt
FF_gain1_expt = -90  # 8000
FF_gain2_expt = 165
FF_gain3_expt = 0
# FF_gain4_expt = -245
FF_gain4_expt = -150
FF_gain2_expt = 125


# yoko69.SetVoltage(-0.2716)
# yoko70.SetVoltage(-0.0754)
# yoko71.SetVoltage(0.0984)
# yoko72.SetVoltage(0.064)

# yoko69.SetVoltage(-0.0938)
# yoko70.SetVoltage(-0.2283)
# yoko71.SetVoltage(-0.0411)
# yoko72.SetVoltage(0.2724)
#
# #Readout Qubit Params
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.7, 'Gain': 11500, "FF_Gains": [0, -15000, 0, -15000]},
#           'Qubit01': {'Frequency':  4703.7 - 0.6, 'Gain': 870},
#           'Qubit12': {'Frequency': 4547.8 + 0.6, 'Gain': 780},
#           'Pulse_FF': [0, -8000, 0, -15000]},
#     # '2': {'Readout': {'Frequency': 7055.65, 'Gain': 8000}, 'Qubit01': {'Frequency': 4701.1, 'Gain': 980},
#     #       'Qubit12': {'Frequency': 4263.3 , 'Gain': 1740},
#     #       'Pulse_FF': [15000, 0, 0, -15000]},
#     '2': {'Readout': {'Frequency': 7055.3, 'Gain': 8000, "FF_Gains": [-11000, 0, 0, -14000]},
#           'Qubit01': {'Frequency': 4431.3, 'Gain': 1000},
#           'Qubit12': {'Frequency': 4274.2, 'Gain': 1800 * 0},
#           'Pulse_FF': [-11000, 0, 0, -14000]},
#     '3': {'Readout': {'Frequency': 7117.05, 'Gain': 6000}, 'Qubit01': {'Frequency': 4420.16, 'Gain': 2100},
#           'Qubit12': {'Frequency': 4230.67, 'Gain': 1160},
#           'Pulse_FF': [-12700, 18000, 0, -14000]},
#     '4': {'Readout': {'Frequency': 7249.6, 'Gain': 7500}, 'Qubit01': {'Frequency': 4670.6, 'Gain': 1550},
#           'Qubit12': {'Frequency': 4516.3 - 0, 'Gain': 970 - 200},
#           'Pulse_FF': [0, 0, 0, -14000]}
#     }

yoko69.SetVoltage(-0.1214)
yoko70.SetVoltage(-0.2226)
yoko71.SetVoltage(-0.2905)
yoko72.SetVoltage(0.2407)

#Readout Qubit Params
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6953, 'Gain': 9500, "FF_Gains": [-20000, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
          'Qubit01': {'Frequency':  4610.4, 'Gain': 1750},
          'Qubit12': {'Frequency': 4458.8, 'Gain': 1},#800},
          'Pulse_FF': [-11000, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7055.8, 'Gain': 7000, "FF_Gains": [0, 17000, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
          'Qubit01': {'Frequency': 4648.5, 'Gain': 1800},
          'Qubit12': {'Frequency': 4494.4, 'Gain': 750 * 0},
          'Pulse_FF': [0, 11000, 0, 0]},
    '3': {'Readout': {'Frequency': 7117.4, 'Gain': 8000, "FF_Gains": [0, 0, 17000, 0]},
          'Qubit01': {'Frequency': 4643.0, 'Gain': 2200},
          'Qubit12': {'Frequency': 4489.8, 'Gain': 1150 * 0},
          'Pulse_FF': [0, 0, 11000, 0]},
    '4': {'Readout': {'Frequency': 7249.7, 'Gain': 8000, "FF_Gains": [0, 0, 0, -23000]},
          'Qubit01': {'Frequency': 4616.7, 'Gain': 2280},
          'Qubit12': {'Frequency': 4463.5, 'Gain': 710 * 0},
          'Pulse_FF': [0, 0, 0, -15000]}
    }

Qubit_Parameters = {
    # '1': {'Readout': {'Frequency': 6953, 'Gain': 9500, "FF_Gains": [-15900, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
    #       'Qubit01': {'Frequency':  4647.8, 'Gain': 1650},
    #       'Qubit12': {'Frequency': 4499.4, 'Gain': 850},
    #       'Pulse_FF': [-8500, 0, 0, 0]},
    # '1': {'Readout': {'Frequency': 6952.6, 'Gain': 9500, "FF_Gains": [-15900, 0, 0, 0], "Readout_Time": 2.5,
    #                   "ADC_Offset": 0.3},
    #       'Qubit01': {'Frequency': 4647.8, 'Gain': 1650},
    #       'Qubit12': {'Frequency': 4499.4, 'Gain': 850},
    #       'Pulse_FF': [-8500, 0, 0, 0]},
    '1': {'Readout': {'Frequency': 6953, 'Gain': 9500, "FF_Gains": [-15900, 0, 0, 0], "Readout_Time": 2.5,
                      "ADC_Offset": 0.3},
          'Qubit01': {'Frequency': 4683.5, 'Gain': 1180},
          'Qubit12': {'Frequency': 4531.2, 'Gain': 770 * 0},
          'Pulse_FF': [-9800, 0, 0, 0]},
    # '2': {'Readout': {'Frequency': 7055.8, 'Gain': 7000, "FF_Gains": [0, 13900, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
    #       'Qubit01': {'Frequency': 4646.6, 'Gain': 1850},
    #       'Qubit12': {'Frequency': 4497.8, 'Gain': 880 * 0},
    #       'Pulse_FF': [0, 7800, 0, 0]},
    #       'Pulse_FF': [0, 7800, 0, 0]},
    '2': {'Readout': {'Frequency': 7055.6, 'Gain': 7500, "FF_Gains": [0, 10000, 0, 0], "Readout_Time": 2.5,
                      "ADC_Offset": 0.3},
          'Qubit01': {'Frequency': 4680.9, 'Gain': 1200},
          'Qubit12': {'Frequency': 4528.3, 'Gain': 830 * 0},
          'Pulse_FF': [0, 9000, 0, 0]},

    '3': {'Readout': {'Frequency': 7117.4, 'Gain': 8000, "FF_Gains": [0, 0, 13600, 0]},
          'Qubit01': {'Frequency': 4654.4, 'Gain': 1770},
          'Qubit12': {'Frequency': 4504.8, 'Gain': 1000 * 0},
          'Pulse_FF': [0, 0, 8000, 0]},
    '4': {'Readout': {'Frequency': 7249.7, 'Gain': 8000, "FF_Gains": [0, 0, 0, -17000]},
          'Qubit01': {'Frequency': 4686.1, 'Gain': 1170},
          'Qubit12': {'Frequency': 4532.5, 'Gain': 700 * 0},
          'Pulse_FF': [0, 0, 0, -12000]}
    }
# #Readout parameters for 12 discrimination
# Qubit_Parameters = {
#     # '1': {'Readout': {'Frequency': 6952.45, 'Gain': 7000, "FF_Gains": [-13000, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
#     #       'Qubit01': {'Frequency':  4683.5, 'Gain': 1180},
#     #       'Qubit12': {'Frequency': 4531.2, 'Gain': 770},
#     #       'Pulse_FF': [-9800, 0, 0, 0]},
#     '1': {'Readout': {'Frequency': 6952.45, 'Gain': 7000, "FF_Gains": [-13000, 0, 0, 0], "Readout_Time": 2.5,
#                       "ADC_Offset": 0.3},
#           'Qubit01': {'Frequency': 4703.4, 'Gain': 890},
#           'Qubit12': {'Frequency': 4550.0, 'Gain': 950},
#           'Pulse_FF': [-10500, 0, 0, 0]},
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
#
# Qubit_Parameters = {
#     '1': {'Readout': {'Frequency': 6952.45, 'Gain': 7000, "FF_Gains": [-13000, 0, 0, 0], "Readout_Time": 2.5, "ADC_Offset": 0.3},
#           'Qubit01': {'Frequency':  4703.4, 'Gain': 890},
#           'Qubit12': {'Frequency': 4550.0, 'Gain': 950},
#           'Pulse_FF': [-10500, 0, 0, 0]},
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
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6953, 'Gain': 9500, "FF_Gains": [-15900, 0, 0, 0], "Readout_Time": 2.5,
                      "ADC_Offset": 0.3},
          'Qubit01': {'Frequency': 4683.5, 'Gain': 1180},
          'Qubit12': {'Frequency': 4531.2, 'Gain': 770 * 0},
          'Pulse_FF': [-9800, 0, 0, 0]},
    '2': {'Readout': {'Frequency': 7055.6, 'Gain': 7500, "FF_Gains": [0, 10000, 0, 0], "Readout_Time": 2.5,
                      "ADC_Offset": 0.3},
          'Qubit01': {'Frequency': 4680.9, 'Gain': 1200},
          'Qubit12': {'Frequency': 4528.3, 'Gain': 830 * 0},
          'Pulse_FF': [0, 9000, 0, 0]},

    '3': {'Readout': {'Frequency': 7117.4, 'Gain': 8000, "FF_Gains": [0, 0, 13600, 0]},
          'Qubit01': {'Frequency': 4654.4, 'Gain': 1770},
          'Qubit12': {'Frequency': 4504.8, 'Gain': 1000 * 0},
          'Pulse_FF': [0, 0, 8000, 0]},
    '4': {'Readout': {'Frequency': 7249.7, 'Gain': 8000, "FF_Gains": [0, 0, 0, -17000]},
          'Qubit01': {'Frequency': 4686.1, 'Gain': 1170},
          'Qubit12': {'Frequency': 4532.5, 'Gain': 700 * 0},
          'Pulse_FF': [0, 0, 0, -12000]}
    }

Qubit_Readout = 2
Qubit_Pulse = 2

# Swaps
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 5000
FF_gain4_expt = -7000


# # expt for 2 photon
# FF_gain1_expt = -140  # 8000
# FF_gain2_expt = 120
# FF_gain3_expt = 0
# FF_gain4_expt = -215

# #Exp for left to right
# FF_gain1_expt = -140  # 8000
# FF_gain2_expt = 140
# FF_gain3_expt = 0
# FF_gain4_expt = -200
#
# #Changes for right to left
# FF_gain4_expt = -260
#
# #Changes for up to down
# FF_gain3_expt = 0
# FF_gain4_expt = -260
# FF_gain2_expt = 190

swept_qubit_index = 2 #1 indexed

Oscillation_Gain = True
oscillation_gain_dict = {'reps': 500, 'start': 0, 'step': int(2 * 16), 'expts': 400, 'gainStart': 0,
                         'gainStop': 200, 'gainNumPoints': 6, 'relax_delay': 200}

Oscillation_Single = False
oscillation_single_dict = {'reps': 3000, 'start': 0, 'step': int(1 * 16), 'expts': 1000, 'relax_delay': 300}

SS_params_2States = {"ground": 0, 'excited': 2, "Shots": 2500, "Readout_Time": 2.5, "ADC_Offset": 0.3}

FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
FF_gain1, FF_gain2, FF_gain3, FF_gain4 = Qubit_Parameters[str(Qubit_Readout)]['Readout']["FF_Gains"]


cavity_gain = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Gain']
resonator_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Readout']['Frequency']
qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']


FF_Qubits[str(1)] |= {'Gain_Readout': FF_gain1, 'Gain_Expt': FF_gain1_expt, 'Gain_Pulse': FF_gain1_pulse}
FF_Qubits[str(2)] |= {'Gain_Readout': FF_gain2, 'Gain_Expt': FF_gain2_expt, 'Gain_Pulse': FF_gain2_pulse}
FF_Qubits[str(3)] |= {'Gain_Readout': FF_gain3, 'Gain_Expt': FF_gain3_expt, 'Gain_Pulse': FF_gain3_pulse}
FF_Qubits[str(4)] |= {'Gain_Readout': FF_gain4, 'Gain_Expt': FF_gain4_expt, 'Gain_Pulse': FF_gain4_pulse}

# Configure for qubit experiment
UpdateConfig_qubit = {
    "qubit_pulse_style": "const",
    "qubit_gain": 1000,
    "qubit_freq": qubit_frequency_center,
    "qubit_length": soc.us2cycles(40),
    ##### define spec slice experiment parameters
    "SpecSpan": 12,  ### MHz, span will be center+/- this parameter
    "SpecNumPoints": 60,  ### number of points in the transmission frequecny
}
UpdateConfig_FF = {
    "ff_pulse_style": "const",  # --Fixed
    "ff_freq": 0,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "ff_nqz": 1,  ### MHz, span will be center+/- this parameter
    "relax_delay": 300,  ### in units us
}
expt_cfg = {
    "center": UpdateConfig_qubit["qubit_freq"],
    "span": UpdateConfig_qubit["SpecSpan"],
    "expts": UpdateConfig_qubit["SpecNumPoints"]
}
expt_cfg["step"] = 2 * expt_cfg["span"] / expt_cfg["expts"]
expt_cfg["start"] = expt_cfg["center"] - expt_cfg["span"]
UpdateConfig_qubit = {**UpdateConfig_qubit, **expt_cfg}

UpdateConfig_transmission = {
    "reps": 1000,  # this will used for all experiements below unless otherwise changed in between trials
    "pulse_style": "const",  # --Fixed
    "readout_length": 2,  # [Clock ticks]
    "pulse_gain": cavity_gain,  # [DAC units]
    "pulse_freq": resonator_frequency_center,  # [MHz] actual frequency is this number + "cavity_LO"
    ##### define tranmission experiment parameters
    "TransSpan": 1.5,  ### MHz, span will be center+/- this parameter
    "TransNumPoints": 60,  ### number of points in the transmission frequecny
}

UpdateConfig = UpdateConfig_transmission | UpdateConfig_qubit | UpdateConfig_FF
config = BaseConfig | UpdateConfig  ### note that UpdateConfig will overwrite elements in BaseConfig
config["FF_Qubits"] = FF_Qubits

#### update the qubit and cavity attenuation

config["rounds"] = 1
config["sigma"] = 0.05

config["shots"] = 2000
config['pulse_expt'] = {"pulse_01": False, "pulse_12": False}
config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Readout)]['Qubit01']['Frequency']
config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Readout)]['Qubit01']['Gain']
config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Readout)]['Qubit12']['Frequency']
config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Readout)]['Qubit12']['Gain']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Readout)]['Pulse_FF']
config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

config["readout_length"] = SS_params_2States["Readout_Time"]  # us (length of the pulse applied)
config["adc_trig_offset"] = SS_params_2States["ADC_Offset"]
Instance_SingleShotProgram = SingleShotProgramFF_2States(path="SingleShot", outerFolder=outerFolder, cfg=config,
                                                         soc=soc, soccfg=soccfg)
data_SingleShotProgram = SingleShotProgramFF_2States.acquire(Instance_SingleShotProgram,
                                                             ground_pulse=SS_params_2States["ground"],
                                                             excited_pulse=SS_params_2States["excited"])
data_SingleShotProgram = SingleShotProgramFF_2States.analyze(Instance_SingleShotProgram, data_SingleShotProgram)

SingleShotProgramFF_2States.display(Instance_SingleShotProgram, data_SingleShotProgram, plotDisp=True)

SingleShotProgramFF_2States.save_data(Instance_SingleShotProgram, data_SingleShotProgram)
SingleShotProgramFF_2States.save_config(Instance_SingleShotProgram)
angle, threshold = data_SingleShotProgram['angle'], data_SingleShotProgram['threshold']
print(angle, threshold)


config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
config["FF_Qubits"]['1']['Gain_Pulse'] = FF_gain1_pulse
config["FF_Qubits"]['2']['Gain_Pulse'] = FF_gain2_pulse
config["FF_Qubits"]['3']['Gain_Pulse'] = FF_gain3_pulse
config["FF_Qubits"]['4']['Gain_Pulse'] = FF_gain4_pulse

if Oscillation_Gain:
    config["reps"] = oscillation_gain_dict['reps']
    expt_cfg = {"start": oscillation_gain_dict['start'], "step": oscillation_gain_dict['step'],
                "expts": oscillation_gain_dict['expts'],
                "pi_gain": qubit_gain, "gainStart": oscillation_gain_dict['gainStart'],
                "gainStop": oscillation_gain_dict['gainStop'], "gainNumPoints": oscillation_gain_dict['gainNumPoints'],
                "qubitIndex": swept_qubit_index, "relax_delay": oscillation_gain_dict['relax_delay'],
                }
    config['IDataArray'] = [1, None, None, None]
    config = config | expt_cfg

    iOscillations = Oscillations_Gain_2nd_SS(path="QubitOscillations_GainSweep_2nd", cfg=config, soc=soc, soccfg=soccfg,
                                      outerFolder=outerFolder)
    dOscillations = Oscillations_Gain_2nd_SS.acquire(iOscillations, angle=angle, threshold= threshold)
    # Oscillations_Gain_2nd_SS.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    Oscillations_Gain_2nd_SS.save_data(iOscillations, dOscillations)


if Oscillation_Single:
    config["reps"] = oscillation_single_dict['reps']
    expt_cfg = {"start": oscillation_single_dict['start'], "step": oscillation_single_dict['step'],
                "expts": oscillation_single_dict['expts'], "relax_delay": oscillation_single_dict['relax_delay']}
    config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
    config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
    config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
    config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']

    config["FF_Qubits"]['1']['Gain_Expt'] = FF_gain1_expt
    config["FF_Qubits"]['2']['Gain_Expt'] = FF_gain2_expt
    config["FF_Qubits"]['3']['Gain_Expt'] = FF_gain3_expt
    config["FF_Qubits"]['4']['Gain_Expt'] = FF_gain4_expt
    #
    config = config | expt_cfg
    config['IDataArray'] = [1, None, None, None]

    iOscillations = WalkFFSS(path="QubitOscillations", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder)
    dOscillations = WalkFFSS.acquire(iOscillations, angle=angle, threshold= threshold)
    WalkFFSS.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
    WalkFFSS.save_data(iOscillations, dOscillations)
print(config)
#
# config['IDataArray'] = [None, None, None, None]


# iOscillations = WalkFF(path="QubitOscillations", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder,
#                        I_Excited=i_excited, I_Ground=i_ground, Q_Excited=q_excited, Q_Ground=q_ground)
# dOscillations = WalkFF.acquire(iOscillations)
# WalkFF.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# WalkFF.save_data(iOscillations, dOscillations)


# config["reps"] = 1300
# expt_cfg = {"start": 0, "step": int(1 * 16) , "expts": 300,
#             "pi_gain": qubit_gain, "relax_delay": 160, 'f_ge': qubit_frequency_center
#             }
#
# config = config | expt_cfg
# print(config)
#
# config['IDataArray'] = [None, None, None, None]


# iOscillations = WalkFF(path="QubitOscillations", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder,
#                        I_Excited=i_excited, I_Ground=i_ground, Q_Excited=q_excited, Q_Ground=q_ground)
# dOscillations = WalkFF.acquire(iOscillations)
# WalkFF.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# WalkFF.save_data(iOscillations, dOscillations)

# qubit_index = 2
# expt_cfg = {"start": 0, "step": int(4 * 16), "expts": 100,
#             "pi_gain": qubit_gain, "gainStart": -400, "gainStop": 0, "gainNumPoints": 25,
#             "qubitIndex": qubit_index, "relax_delay": 150,
#             }
# config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
# config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
# config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
# config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain']
#
# config['IDataArray'] = [1, None, None, None]
#
# config = config | expt_cfg
#
# iOscillations = Oscillations_Gain_2nd(path="QubitOscillations_GainSweep_2nd", cfg=config, soc=soc, soccfg=soccfg,
#                                   outerFolder=outerFolder, I_Excited=1, I_Ground=0,
#                                   Q_Excited=1, Q_Ground=0)
# dOscillations = Oscillations_Gain_2nd.acquire(iOscillations)
# # Oscillations_Gain_2nd.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# Oscillations_Gain_2nd.save_data(iOscillations, dOscillations)




# ARabi_config = {"sigma": 0.05, "f_ge": qubit_frequency_center}
#
# # config = config | ARabi_config
#
# qubit_gain = Qubit_Parameters[str(Qubit_Readout)]['Qubit']['Gain']
# qubit_frequency_center = Qubit_Parameters[str(Qubit_Readout)]['Qubit']['Frequency']
# FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Readout)]['Pulse_FF']
# config["FF_Qubits"][str(1)]["Gain_Pulse"] = FF_gain1_pulse
# config["FF_Qubits"][str(2)]["Gain_Pulse"] = FF_gain2_pulse
# config["FF_Qubits"][str(3)]["Gain_Pulse"] = FF_gain3_pulse
# config["FF_Qubits"][str(4)]["Gain_Pulse"] = FF_gain4_pulse

#
# number_of_steps = 2
# config["reps"] = 3000
# step = int(qubit_gain * 2 / number_of_steps)
# ARabi_config = {'start': 0, 'step': step, "expts": number_of_steps,
#                 "sigma":ARabi_config["sigma"],"f_ge": qubit_frequency_center, "relax_delay": 250}
# config = config | ARabi_config ### note that UpdateConfig will overwrite elements in BaseConfig
# iAmpRabi = AmplitudeRabiFF(path="AmplitudeRabi", cfg=config,soc=soc,soccfg=soccfg,
#                             outerFolder=outerFolder)
# dAmpRabi = AmplitudeRabiFF.acquire(iAmpRabi)
# AmplitudeRabiFF.display(iAmpRabi, dAmpRabi, plotDisp=True, figNum=2)
# AmplitudeRabiFF.save_data(iAmpRabi, dAmpRabi)
# avgi = dAmpRabi['data']['avgi'][0][0]
# avgq = dAmpRabi['data']['avgq'][0][0]
# i_ground, i_excited = avgi[0], avgi[1]
# q_ground, q_excited = avgq[0], avgq[1]
#
# i_data_range = np.abs(i_excited - i_ground)
# q_data_range = np.abs(q_excited - q_ground)
# if i_data_range > q_data_range:
#     IData = True
#     ADC_ground = i_ground
#     ADC_excited = i_excited
# else:
#     IData = False
#     ADC_ground = q_ground
#     ADC_excited = q_excited


# qubit_gain = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Gain']
# qubit_frequency_center = Qubit_Parameters[str(Qubit_Pulse)]['Qubit']['Frequency']
# FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']
# config["FF_Qubits"][str(1)]["Gain_Pulse"] = FF_gain1_pulse
# config["FF_Qubits"][str(2)]["Gain_Pulse"] = FF_gain2_pulse
# config["FF_Qubits"][str(3)]["Gain_Pulse"] = FF_gain3_pulse
# config["FF_Qubits"][str(4)]["Gain_Pulse"] = FF_gain4_pulse

# config["reps"] = 1300
# expt_cfg = {"start": 0, "step": int(1 * 16) , "expts": 300,
#             "pi_gain": qubit_gain, "relax_delay": 160, 'f_ge': qubit_frequency_center
#             }
#
# config = config | expt_cfg
# print(config)
#
# config['IDataArray'] = [None, None, None, None]


# iOscillations = WalkFF(path="QubitOscillations", cfg=config, soc=soc, soccfg=soccfg, outerFolder=outerFolder,
#                        I_Excited=i_excited, I_Ground=i_ground, Q_Excited=q_excited, Q_Ground=q_ground)
# dOscillations = WalkFF.acquire(iOscillations)
# WalkFF.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# WalkFF.save_data(iOscillations, dOscillations)


#
# qubit_index = 1 #1 indexed
#
# expt_cfg = {"start": 4000, "step": int(1 * 16), "expts": 300,
#             "pi_gain": qubit_gain, "gainStart": -50, "gainStop": 250, "gainNumPoints": 7,
#             "qubitIndex": qubit_index, "relax_delay": 150,
#             }
# # expt_cfg = {"start": 0, "step": int(1.5 * 16), "expts": 250,
# #             "pi_gain": qubit_gain, "gainStart": -1000, "gainStop": 1000, "gainNumPoints": 81,
# #             "qubitIndex": qubit_index, "relax_delay": 150,
# #             }
# config['f_ge'] = qubit_frequency_center
#
#
# config['IDataArray'] = [None, None, None, None]
# # config['IDataArray'] = [None, None, None, None]
# config["reps"] = 50
#
#
#
# config = config | expt_cfg
# print(config)
#
# iOscillations = Oscillations_Gain(path="QubitOscillations_GainSweep", cfg=config, soc=soc, soccfg=soccfg,
#                                   outerFolder=outerFolder, I_Excited=i_excited, I_Ground=i_ground,
#                                   Q_Excited=q_excited, Q_Ground=q_ground)
# dOscillations = Oscillations_Gain.acquire(iOscillations)
# Oscillations_Gain.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
# Oscillations_Gain.save_data(iOscillations, dOscillations)
#

