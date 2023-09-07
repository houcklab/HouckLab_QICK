# os.add_dll_directory(os.getcwd() + '\\PythonDrivers')
# os.add_dll_directory(os.getcwd() + '.\..\\')

from q4diamond.Client_modules.initialize import *
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillations import WalkFF
from q4diamond.Client_modules.Experiment_Scripts.mAmplitudeRabiFF import AmplitudeRabiFF
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillations_GainSweep import Oscillations_Gain
from q4diamond.Client_modules.Experiment_Scripts.mRabiOscillations_2nd_GainSweep import Oscillations_Gain_2nd

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

# yoko69.SetVoltage(-0.2716)
# yoko70.SetVoltage(-0.0754)
# yoko71.SetVoltage(0.0984)
# yoko72.SetVoltage(0.064)

yoko69.SetVoltage(-0.2716)
yoko70.SetVoltage(-0.0754)
yoko71.SetVoltage(0.0984)
yoko72.SetVoltage(0.064)

#Readout Qubit Params
Qubit_Parameters = {
    '1': {'Readout': {'Frequency': 6952.7, 'Gain': 11500}, 'Qubit01': {'Frequency':  4703.7, 'Gain': 870},
          'Qubit12': {'Frequency': 4547.8, 'Gain': 780},
          'Pulse_FF': [0, -15000, 0, -15000]},
    '2': {'Readout': {'Frequency': 7055.65, 'Gain': 8000}, 'Qubit01': {'Frequency': 4701.1, 'Gain': 980},
          'Qubit12': {'Frequency': 4263.3 , 'Gain': 1740},
          'Pulse_FF': [15000, 0, 0, -15000]},
    '3': {'Readout': {'Frequency': 7117.05, 'Gain': 6000}, 'Qubit01': {'Frequency': 4420.16, 'Gain': 2100},
          'Qubit12': {'Frequency': 4230.67, 'Gain': 1160},
          'Pulse_FF': [-12700, 18000, 0, -14000]},
    '4': {'Readout': {'Frequency': 7249.6, 'Gain': 7500}, 'Qubit01': {'Frequency': 4670.6, 'Gain': 1550},
          'Qubit12': {'Frequency': 4516.3 - 0, 'Gain': 970 - 200},
          'Pulse_FF': [0, 0, 0, -14000]}
    }

Qubit_Readout = 1
Qubit_Pulse = 1
# Readout
FF_gain1 = 0  # 8000
FF_gain2 = -15000
FF_gain3 = 0
FF_gain4 = -15000

# expt
FF_gain1_expt = 0  # 8000
FF_gain2_expt = 0
FF_gain3_expt = 0
FF_gain4_expt = -15000


FF_gain1_pulse, FF_gain2_pulse, FF_gain3_pulse, FF_gain4_pulse = Qubit_Parameters[str(Qubit_Pulse)]['Pulse_FF']

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
    "relax_delay": 200,  ### in units us
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

config["reps"] = 1500
config["rounds"] = 1
config["sigma"] = 0.05


qubit_index = 2
expt_cfg = {"start": 0, "step": int(2 * 16), "expts": 65,
            "pi_gain": qubit_gain, "gainStart": -1500, "gainStop": 1500, "gainNumPoints": 41,
            "qubitIndex": qubit_index, "relax_delay": 150,
            }
config['qubit_freq01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Frequency']
config['qubit_gain01'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit01']['Gain']
config['qubit_freq12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Frequency']
config['qubit_gain12'] = Qubit_Parameters[str(Qubit_Pulse)]['Qubit12']['Gain'] * 0

config['IDataArray'] = [1, None, None, None]

config = config | expt_cfg

iOscillations = Oscillations_Gain_2nd(path="QubitOscillations_GainSweep_2nd", cfg=config, soc=soc, soccfg=soccfg,
                                  outerFolder=outerFolder, I_Excited=1, I_Ground=0,
                                  Q_Excited=1, Q_Ground=0)
dOscillations = Oscillations_Gain_2nd.acquire(iOscillations)
# Oscillations_Gain_2nd.display(iOscillations, dOscillations, plotDisp=True, figNum=2)
Oscillations_Gain_2nd.save_data(iOscillations, dOscillations)




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

